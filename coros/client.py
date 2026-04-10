"""
Coros client for uploading activities
"""
import hashlib
import json
import logging
import os
import zipfile
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import certifi
import urllib3

from config.settings import FIT_DIR

logger = logging.getLogger(__name__)


# Region configuration
REGION_CONFIG = {
    1: {"teamapi": "https://teamapi.coros.com", "env": "en.prod"},
    2: {"teamapi": "https://teamcnapi.coros.com", "env": "cn.prod"},
    3: {"teamapi": "https://teameuapi.coros.com", "env": "eu.prod"},
}

# STS configuration
STS_CONFIG = {
    1: {"bucket": "coros-s3", "service": "aws"},
    2: {"bucket": "coros-oss", "service": "aliyun"},
    3: {"bucket": "eu-coros", "service": "aws"},
}


class CorosClient:
    """Coros API client"""

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.access_token = None
        self.user_id = None
        self.region_id = None
        self.teamapi = None
        self.req = urllib3.PoolManager(
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where()
        )
        self._login()

    def _login(self):
        """Login to Coros"""
        login_url = f"{REGION_CONFIG[2]['teamapi']}/account/login"  # CN region default

        login_data = {
            "account": self.email,
            "pwd": hashlib.md5(self.password.encode()).hexdigest(),
            "accountType": 2,
        }

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "referer": "https://teamcnapi.coros.com/",
            "origin": "https://teamcnapi.coros.com/",
        }

        response = self.req.request(
            "POST",
            login_url,
            body=json.dumps(login_data).encode(),
            headers=headers
        )

        login_response = json.loads(response.data)
        if login_response["result"] != "0000":
            raise Exception(f"Coros login failed: {login_response.get('message', 'Unknown error')}")

        self.access_token = login_response["data"]["accessToken"]
        self.user_id = login_response["data"]["userId"]
        self.region_id = login_response["data"]["regionId"]
        self.teamapi = REGION_CONFIG.get(self.region_id, REGION_CONFIG[2])["teamapi"]

        logger.info(f"Logged in to Coros: user_id={self.user_id}, region_id={self.region_id}")

    def _get_oss_client(self):
        """Get appropriate OSS client based on region"""
        if self.region_id == 2:
            return AliOssClient()
        else:
            return AwsOssClient()

    def _create_zip(self, fit_data: bytes, activity_id: int) -> bytes:
        """Create zip file from FIT data"""
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{activity_id}.fit", fit_data)
        return buffer.getvalue()

    def _extract_fit_from_garmin_zip(self, zip_data: bytes, activity_id: int) -> bytes:
        """Extract FIT file from Garmin's ZIP download.

        Garmin Connect returns a ZIP containing the FIT file.
        We need to extract the inner FIT file and re-zip it for Coros.
        """
        try:
            with zipfile.ZipFile(BytesIO(zip_data)) as zf:
                # Find the .fit file inside
                for name in zf.namelist():
                    if name.lower().endswith('.fit'):
                        fit_data = zf.read(name)
                        logger.debug(f"Extracted {name} ({len(fit_data)} bytes) from Garmin ZIP")
                        return fit_data
                # If no .fit found, return as-is (might already be raw FIT)
                logger.warning("No .fit file found in Garmin ZIP, treating as raw FIT")
                return zip_data
        except zipfile.BadZipFile:
            # Not a ZIP, assume raw FIT data
            logger.warning("Garmin download was not a ZIP, treating as raw FIT")
            return zip_data

    def _oss_key(self, activity_id: int, zip_md5: str) -> str:
        """Generate OSS object key for Coros"""
        return f"fit_zip/{self.user_id}/{zip_md5}.zip"

    def upload_activity(self, activity_id: int, fit_data: bytes) -> bool:
        """Upload activity to Coros"""
        try:
            # Extract FIT from Garmin's ZIP format if needed
            fit_data = self._extract_fit_from_garmin_zip(fit_data, activity_id)

            # Create zip from FIT data
            zip_data = self._create_zip(fit_data, activity_id)
            zip_size = len(zip_data)

            # Get MD5 of zip
            zip_md5 = hashlib.md5(zip_data).hexdigest()
            logger.info(f"Created zip: {zip_size} bytes, md5={zip_md5}")

            # Upload to OSS
            logger.info("Uploading to OSS...")
            oss_client = self._get_oss_client()
            oss_key = self._oss_key(activity_id, zip_md5)
            oss_object = oss_client.multipart_upload(
                zip_data,
                oss_key
            )
            logger.info(f"OSS upload complete: {oss_object}")

            # Notify Coros to import
            upload_url = f"{self.teamapi}/activity/fit/import"
            sts_config = STS_CONFIG.get(self.region_id, STS_CONFIG[2])

            headers = {
                "Accept": "application/json, text/plain, */*",
                "accesstoken": self.access_token,
            }

            data = {
                "source": 1,
                "timezone": 32,
                "bucket": sts_config["bucket"],
                "md5": zip_md5,
                "size": zip_size,
                "object": oss_object,
                "serviceName": sts_config["service"],
                "oriFileName": f"{activity_id}.zip",
            }

            logger.info(f"Sending import request to Coros: {upload_url}")
            response = self.req.request(
                "POST",
                upload_url,
                fields={"jsonParameter": json.dumps(data)},
                headers=headers
            )

            logger.info(f"Coros response status: {response.status}")
            logger.info(f"Coros response data: {response.data}")

            if not response.data:
                logger.error("Empty response from Coros")
                return False

            upload_response = json.loads(response.data)
            logger.info(f"Upload response: {upload_response}")

            # status=2 means success
            return (
                upload_response.get("data", {}).get("status") == 2
                and upload_response.get("result") == "0000"
            )

        except Exception as e:
            logger.error(f"Error uploading activity {activity_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def get_activities(self, size: int = 200, page: int = 1) -> dict:
        """Query Coros activities (paginated).

        Returns dict with dataList and pagination info.
        """
        try:
            url = f"{self.teamapi}/activity/query?size={size}&pageNumber={page}"
            headers = {
                "Accept": "application/json, text/plain, */*",
                "accesstoken": self.access_token,
            }
            response = self.req.request("GET", url, headers=headers)
            return json.loads(response.data)
        except Exception as e:
            logger.error(f"Error fetching Coros activities: {e}")
            return {"data": {"dataList": [], "count": 0}}

    def get_all_activities(self) -> List[dict]:
        """Get all Coros activities (paginated)."""
        all_activities = []
        page = 1
        size = 200

        while True:
            result = self.get_activities(size=size, page=page)
            data_list = result.get("data", {}).get("dataList", [])
            if not data_list:
                break
            all_activities.extend(data_list)
            total_count = result.get("data", {}).get("count", 0)
            if len(all_activities) >= total_count:
                break
            page += 1
            logger.debug(f"Fetched {len(all_activities)}/{total_count} activities")

        return all_activities

    def download_activity(self, label_id: str, sport_type: int) -> Optional[bytes]:
        """Download FIT file from Coros.

        Args:
            label_id: Activity labelId from Coros
            sport_type: Sport type ID

        Returns:
            FIT file bytes, or None on failure
        """
        try:
            # Get download URL
            url = f"{self.teamapi}/activity/detail/download?labelId={label_id}&sportType={sport_type}&fileType=4"
            headers = {
                "Accept": "application/json, text/plain, */*",
                "accesstoken": self.access_token,
            }
            response = self.req.request("POST", url, headers=headers)
            resp_data = json.loads(response.data)

            download_url = resp_data.get("data", {}).get("fileUrl")
            if not download_url:
                logger.error(f"No download URL in Coros response: {resp_data}")
                return None

            # Download the FIT file
            file_response = self.req.request("GET", download_url, headers=headers)
            if file_response.status != 200:
                logger.error(f"Failed to download FIT from Coros: status={file_response.status}")
                return None

            return file_response.data

        except Exception as e:
            logger.error(f"Error downloading Coros activity {label_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None


class AliOssClient:
    """Aliyun OSS client for Coros China"""

    def __init__(self):
        import oss2
        self.oss2 = oss2
        self.bucket = "coros-oss"
        self.service = "aliyun"
        self.app_id = "1660188068672619112"
        self.sign = "9AD4AA35AAFEE6BB1E847A76848D58DF"
        self.v = 2
        self.req = urllib3.PoolManager(
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where()
        )
        self._init_client()

    def _init_client(self):
        """Initialize OSS client"""
        import oss2
        from oss2 import SizedFileAdapter, determine_part_size
        from oss2.models import PartInfo

        # Get STS token
        sts_url = (
            f"https://faq.coros.com/openapi/oss/sts"
            f"?bucket={self.bucket}&service={self.service}"
            f"&app_id={self.app_id}&sign={self.sign}&v={self.v}"
        )

        response = self.req.request("GET", sts_url)
        sts_response = json.loads(response.data)

        if sts_response["code"] != 200:
            raise Exception("Failed to get OSS STS token")

        credentials = sts_response["data"]["credentials"]

        # Decode credentials: remove salt first, then base64 decode
        import base64
        salt = "9y78gpoERW4lBNYL"
        encoded_cred = credentials.replace(salt, '')
        decoded = base64.b64decode(encoded_cred).decode('utf-8')
        creds = json.loads(decoded)

        security_token = creds["SecurityToken"]
        access_key_id = creds["AccessKeyId"]
        access_key_secret = creds["AccessKeySecret"]

        auth = oss2.StsAuth(access_key_id, access_key_secret, security_token)
        self.bucket = oss2.Bucket(auth, "https://oss-cn-beijing.aliyuncs.com", self.bucket)

    def multipart_upload(self, data: bytes, key: str) -> str:
        """Upload data using multipart"""
        import oss2
        from oss2 import SizedFileAdapter, determine_part_size
        from oss2.models import PartInfo

        total_size = len(data)
        part_size = determine_part_size(total_size, preferred_size=1024 * 1024)
        parts = []

        # Init multipart upload
        upload_id = self.bucket.init_multipart_upload(key).upload_id

        try:
            with BytesIO(data) as fileobj:
                part_number = 1
                offset = 0
                while offset < total_size:
                    num_to_upload = min(part_size, total_size - offset)
                    result = self.bucket.upload_part(
                        key,
                        upload_id,
                        part_number,
                        SizedFileAdapter(fileobj, num_to_upload)
                    )
                    parts.append(PartInfo(part_number, result.etag))
                    offset += num_to_upload
                    part_number += 1

            self.bucket.complete_multipart_upload(key, upload_id, parts)
            return key

        except Exception as e:
            # Abort multipart upload on error
            self.bucket.abort_multipart_upload(key, upload_id)
            raise e


class AwsOssClient:
    """AWS S3 client for Coros international"""

    def __init__(self):
        import boto3
        self.boto3 = boto3
        self.bucket = "coros-s3"
        self.region = "us-east-1"
        self._init_client()

    def _init_client(self):
        """Initialize S3 client"""
        # TODO: Implement AWS STS token fetch and S3 upload
        raise NotImplementedError("AWS S3 upload not yet implemented")
