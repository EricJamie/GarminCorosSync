import unittest
from unittest import mock
from pathlib import Path

from garmin.client import GarminClient, GarminTokenExpiredError


class GarminClientTestCase(unittest.TestCase):
    @mock.patch("garmin.client.GarminClient._connect")
    def test_constructor_preserves_credentials(self, mocked_connect):
        client = GarminClient(email="user@example.com", password="pw", token_data="")

        self.assertEqual(client.email, "user@example.com")
        self.assertEqual(client.password, "pw")
        mocked_connect.assert_called_once()

    @mock.patch("garminconnect.Garmin")
    def test_email_password_login_uses_constructor_then_login(self, garmin_cls):
        garmin_instance = mock.Mock()
        garmin_cls.return_value = garmin_instance

        client = GarminClient.__new__(GarminClient)
        client.email = "user@example.com"
        client.password = "pw"
        client.token_data = ""
        client.tokenstore = ""

        with mock.patch.object(GarminClient, "_discover_tokenstore", return_value=None), \
                mock.patch.object(GarminClient, "_resolve_tokenstore_write_path", return_value="C:/Users/A/.garminconnect/default/garmin_tokens.json"):
            GarminClient._connect(client)

        garmin_cls.assert_called_once_with("user@example.com", "pw")
        garmin_instance.login.assert_called_once_with("C:/Users/A/.garminconnect/default/garmin_tokens.json")

    @mock.patch("garminconnect.Garmin")
    def test_token_login_passes_token_data_to_login(self, garmin_cls):
        garmin_instance = mock.Mock()
        garmin_cls.return_value = garmin_instance

        client = GarminClient.__new__(GarminClient)
        client.email = ""
        client.password = ""
        client.token_data = "x" * 1024
        client.tokenstore = ""

        GarminClient._connect(client)

        garmin_cls.assert_called_once_with()
        garmin_instance.login.assert_called_once_with("x" * 1024)

    @mock.patch("garminconnect.Garmin")
    def test_tokenstore_login_is_preferred_before_password(self, garmin_cls):
        garmin_instance = mock.Mock()
        garmin_cls.return_value = garmin_instance

        client = GarminClient.__new__(GarminClient)
        client.email = "user@example.com"
        client.password = "pw"
        client.token_data = ""
        client.tokenstore = ""

        with mock.patch.object(GarminClient, "_discover_tokenstore", return_value="C:/Users/A/.garminconnect/1/garmin_tokens.json"):
            GarminClient._connect(client)

        garmin_cls.assert_called_once_with("user@example.com", "pw")
        garmin_instance.login.assert_called_once_with("C:/Users/A/.garminconnect/1/garmin_tokens.json")

    @mock.patch("garminconnect.Garmin")
    def test_tokenstore_failure_falls_back_to_password_and_refreshes_tokenstore(self, garmin_cls):
        tokenstore_instance = mock.Mock()
        tokenstore_instance.login.side_effect = RuntimeError("token expired")
        password_instance = mock.Mock()
        garmin_cls.side_effect = [tokenstore_instance, password_instance]

        client = GarminClient.__new__(GarminClient)
        client.Garmin = garmin_cls
        client.email = "user@example.com"
        client.password = "pw"
        client.token_data = ""
        client.tokenstore = ""

        with mock.patch.object(GarminClient, "_discover_tokenstore", return_value="C:/Users/A/.garminconnect/1/garmin_tokens.json"), \
                mock.patch.object(GarminClient, "_resolve_tokenstore_write_path", return_value="C:/Users/A/.garminconnect/default/garmin_tokens.json"):
            GarminClient._connect(client)

        self.assertEqual(garmin_cls.call_args_list[0], mock.call("user@example.com", "pw"))
        self.assertEqual(garmin_cls.call_args_list[1], mock.call("user@example.com", "pw"))
        tokenstore_instance.login.assert_called_once_with("C:/Users/A/.garminconnect/1/garmin_tokens.json")
        password_instance.login.assert_called_once_with("C:/Users/A/.garminconnect/default/garmin_tokens.json")

    @mock.patch("garminconnect.Garmin")
    def test_token_data_failure_falls_back_to_password_and_refreshes_tokenstore(self, garmin_cls):
        token_instance = mock.Mock()
        token_instance.login.side_effect = RuntimeError("token invalid")
        password_instance = mock.Mock()
        garmin_cls.side_effect = [token_instance, password_instance]

        client = GarminClient.__new__(GarminClient)
        client.Garmin = garmin_cls
        client.email = "user@example.com"
        client.password = "pw"
        client.token_data = "x" * 1024
        client.tokenstore = ""

        with mock.patch.object(GarminClient, "_discover_tokenstore", return_value=None), \
                mock.patch.object(GarminClient, "_resolve_tokenstore_write_path", return_value="C:/Users/A/.garminconnect/default/garmin_tokens.json"):
            GarminClient._connect(client)

        self.assertEqual(garmin_cls.call_args_list[0], mock.call())
        self.assertEqual(garmin_cls.call_args_list[1], mock.call("user@example.com", "pw"))
        token_instance.login.assert_called_once_with("x" * 1024)
        password_instance.login.assert_called_once_with("C:/Users/A/.garminconnect/default/garmin_tokens.json")

    def test_default_tokenstore_write_path_uses_home_directory(self):
        client = GarminClient.__new__(GarminClient)
        client.tokenstore = ""

        with mock.patch("garmin.client.Path.home", return_value=Path("C:/Users/A")), \
                mock.patch("pathlib.Path.mkdir", return_value=None):
            path = GarminClient._resolve_tokenstore_write_path(client)

        self.assertEqual(path, "C:\\Users\\A\\.garminconnect\\default\\garmin_tokens.json")

    def test_dump_tokenstore_uses_underlying_client_dump(self):
        inner_client = mock.Mock()
        outer_client = mock.Mock()
        outer_client.client = inner_client

        client = GarminClient.__new__(GarminClient)
        client.client = outer_client
        client.tokenstore = ""

        with mock.patch.object(GarminClient, "_resolve_tokenstore_write_path", return_value="C:/Users/A/.garminconnect/default/garmin_tokens.json"):
            saved_path = GarminClient.dump_tokenstore(client)

        inner_client.dump.assert_called_once_with("C:/Users/A/.garminconnect/default/garmin_tokens.json")
        self.assertEqual(saved_path, "C:/Users/A/.garminconnect/default/garmin_tokens.json")

    def test_export_token_data_uses_underlying_client_dumps(self):
        inner_client = mock.Mock()
        inner_client.dumps.return_value = '{"di_token":"abc"}'
        outer_client = mock.Mock()
        outer_client.client = inner_client

        client = GarminClient.__new__(GarminClient)
        client.client = outer_client

        token_json = GarminClient.export_token_data(client)

        inner_client.dumps.assert_called_once_with()
        self.assertEqual(token_json, '{"di_token":"abc"}')

    def test_refresh_tokenstore_uses_underlying_refresh_when_available(self):
        inner_client = mock.Mock()
        outer_client = mock.Mock()
        outer_client.client = inner_client

        client = GarminClient.__new__(GarminClient)
        client.client = outer_client
        client.tokenstore = ""

        with mock.patch.object(GarminClient, "_resolve_tokenstore_write_path", return_value="C:/Users/A/.garminconnect/default/garmin_tokens.json"):
            saved_path = GarminClient.refresh_tokenstore(client)

        inner_client._refresh_session.assert_called_once_with()
        inner_client.dump.assert_called_once_with("C:/Users/A/.garminconnect/default/garmin_tokens.json")
        self.assertEqual(saved_path, "C:/Users/A/.garminconnect/default/garmin_tokens.json")

    def test_refresh_tokenstore_falls_back_to_dump_without_refresh_api(self):
        class InnerClientNoRefresh:
            def __init__(self):
                self.dump = mock.Mock()

        inner_client = InnerClientNoRefresh()
        outer_client = mock.Mock()
        outer_client.client = inner_client

        client = GarminClient.__new__(GarminClient)
        client.client = outer_client
        client.tokenstore = ""

        with mock.patch.object(GarminClient, "_resolve_tokenstore_write_path", return_value="C:/Users/A/.garminconnect/default/garmin_tokens.json"):
            saved_path = GarminClient.refresh_tokenstore(client)

        inner_client.dump.assert_called_once_with("C:/Users/A/.garminconnect/default/garmin_tokens.json")
        self.assertEqual(saved_path, "C:/Users/A/.garminconnect/default/garmin_tokens.json")

    def test_is_token_error_matches_common_expiration_messages(self):
        self.assertTrue(GarminClient._is_token_error(RuntimeError("token expired")))
        self.assertTrue(GarminClient._is_token_error(RuntimeError("Failed to retrieve social profile")))
        self.assertFalse(GarminClient._is_token_error(RuntimeError("network timeout")))

    @mock.patch("garminconnect.Garmin")
    def test_tokenstore_failure_without_password_raises_token_error(self, garmin_cls):
        garmin_instance = mock.Mock()
        garmin_instance.login.side_effect = RuntimeError("token expired")
        garmin_cls.return_value = garmin_instance

        client = GarminClient.__new__(GarminClient)
        client.Garmin = garmin_cls
        client.email = ""
        client.password = ""
        client.token_data = ""
        client.tokenstore = ""

        with mock.patch.object(GarminClient, "_discover_tokenstore", return_value="C:/Users/A/.garminconnect/1/garmin_tokens.json"):
            with self.assertRaises(GarminTokenExpiredError):
                GarminClient._connect(client)


if __name__ == "__main__":
    unittest.main()
