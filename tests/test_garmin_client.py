import unittest
from unittest import mock

from garmin.client import GarminClient, GarminTokenExpiredError


class GarminClientTestCase(unittest.TestCase):
    @mock.patch("garmin.client.GarminClient._connect")
    def test_constructor_preserves_credentials(self, mocked_connect):
        client = GarminClient(email="user@example.com", password="pw", token_data="")

        self.assertEqual(client.email, "user@example.com")
        self.assertEqual(client.password, "pw")
        self.assertIs(client.client, client)
        mocked_connect.assert_called_once()

    @mock.patch("garmin.client.VendoredGarminClient")
    def test_email_password_login_uses_vendored_client(self, vendored_cls):
        vendored = mock.Mock()
        vendored_cls.return_value = vendored

        client = GarminClient.__new__(GarminClient)
        client.email = "user@example.com"
        client.password = "pw"
        client.token_data = ""
        client.prompt_mfa = None
        client._client = None
        client.client = client

        GarminClient._login_with_password(client)

        vendored_cls.assert_called_once_with()
        vendored.login.assert_called_once_with("user@example.com", "pw", prompt_mfa=None)

    @mock.patch("garmin.client.VendoredGarminClient")
    def test_token_login_loads_json_into_vendored_client(self, vendored_cls):
        vendored = mock.Mock()
        vendored_cls.return_value = vendored

        client = GarminClient.__new__(GarminClient)
        client.email = ""
        client.password = ""
        client.token_data = "x" * 1024
        client.prompt_mfa = None
        client._client = None
        client.client = client

        GarminClient._login_with_token_data(client)

        vendored_cls.assert_called_once_with()
        vendored.loads.assert_called_once_with("x" * 1024)
        vendored._load_profile.assert_called_once_with()

    @mock.patch("garmin.client.VendoredGarminClient")
    def test_token_data_failure_falls_back_to_password(self, vendored_cls):
        token_client = mock.Mock()
        token_client.loads.side_effect = RuntimeError("token invalid")
        password_client = mock.Mock()
        vendored_cls.side_effect = [token_client, password_client]

        client = GarminClient.__new__(GarminClient)
        client.email = "user@example.com"
        client.password = "pw"
        client.token_data = "x" * 1024
        client.prompt_mfa = None
        client._client = None
        client.client = client

        GarminClient._connect(client)

        self.assertEqual(vendored_cls.call_args_list[0], mock.call())
        self.assertEqual(vendored_cls.call_args_list[1], mock.call())
        token_client.loads.assert_called_once_with("x" * 1024)
        password_client.login.assert_called_once_with("user@example.com", "pw", prompt_mfa=None)

    def test_export_token_data_uses_vendored_dumps(self):
        vendored = mock.Mock()
        vendored.dumps.return_value = '{"di_token":"abc"}'

        client = GarminClient.__new__(GarminClient)
        client._client = vendored

        token_json = GarminClient.export_token_data(client)

        vendored.dumps.assert_called_once_with()
        self.assertEqual(token_json, '{"di_token":"abc"}')

    def test_is_token_error_matches_common_messages(self):
        self.assertTrue(GarminClient._is_token_error(RuntimeError("token expired")))
        self.assertTrue(GarminClient._is_token_error(RuntimeError("Too Many Requests")))
        self.assertFalse(GarminClient._is_token_error(RuntimeError("network timeout")))

    @mock.patch("garmin.client.VendoredGarminClient")
    def test_token_failure_without_password_raises_token_error(self, vendored_cls):
        token_client = mock.Mock()
        token_client.loads.side_effect = RuntimeError("token expired")
        vendored_cls.return_value = token_client

        client = GarminClient.__new__(GarminClient)
        client.email = ""
        client.password = ""
        client.token_data = "x" * 1024
        client.prompt_mfa = None
        client._client = None
        client.client = client

        with self.assertRaises(GarminTokenExpiredError):
            GarminClient._connect(client)


if __name__ == "__main__":
    unittest.main()
