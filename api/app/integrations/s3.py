import math
from functools import lru_cache

import boto3
from botocore.config import Config
from app.core.config import settings


def _client(endpoint_url: str):
    return boto3.client(
        's3',
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        endpoint_url=endpoint_url,
        region_name='us-east-1',
        # RustFS는 기본적으로 path-style 주소만 지원 (http://host/bucket/key)
        config=Config(s3={'addressing_style': 'path'}, signature_version='s3v4'),
    )


@lru_cache(maxsize=16)
def _public_client(endpoint_url: str):
    """브라우저용 서명 URL 은 브라우저가 접속할 주소로 서명해야 하므로 주소별 클라이언트를 둡니다."""
    return _client(endpoint_url)


class S3Provider:
    def __init__(self):
        self.client = _client(settings.MLFLOW_S3_ENDPOINT_URL)  # http://rustfs:9000

    def list_buckets(self):
        response = self.client.list_buckets()
        return [b['Name'] for b in response.get('Buckets', [])]

    def browse_objects(self, bucket_name: str, prefix: str = ""):
        return self.client.list_objects_v2(
            Bucket=bucket_name, 
            Prefix=prefix, 
            Delimiter='/'
        )

    # ---------------------------------------------------------------- 데이터셋 업로드
    def ensure_upload_cors(self, bucket: str):
        origins = [o.strip() for o in settings.S3_CORS_ALLOWED_ORIGINS.split(",") if o.strip()]
        self.client.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": [{
            "AllowedOrigins": origins or ["*"],
            "AllowedMethods": ["PUT", "GET", "HEAD"],
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag"],   # 나눠 올리기 완료에 각 조각의 ETag 가 필요
            "MaxAgeSeconds": 3600,
        }]})

    def presign_put(self, endpoint: str, bucket: str, key: str, expires: int) -> str:
        return _public_client(endpoint).generate_presigned_url(
            "put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires)

    def start_multipart(self, endpoint: str, bucket: str, key: str, size: int, expires: int):
        part_size = max(settings.UPLOAD_PART_SIZE, math.ceil(size / 10000 / (1 << 20)) * (1 << 20))
        n_parts = max(1, math.ceil(size / part_size))
        upload_id = self.client.create_multipart_upload(Bucket=bucket, Key=key)["UploadId"]
        pub = _public_client(endpoint)
        parts = [{
            "part_number": n,
            "url": pub.generate_presigned_url(
                "upload_part",
                Params={"Bucket": bucket, "Key": key, "UploadId": upload_id, "PartNumber": n},
                ExpiresIn=expires),
        } for n in range(1, n_parts + 1)]
        return upload_id, part_size, parts

    def complete_multipart(self, bucket: str, key: str, upload_id: str, parts):
        self.client.complete_multipart_upload(
            Bucket=bucket, Key=key, UploadId=upload_id,
            MultipartUpload={"Parts": [{"PartNumber": p.part_number, "ETag": p.etag}
                                       for p in sorted(parts, key=lambda p: p.part_number)]})

    def abort_multipart(self, bucket: str, key: str, upload_id: str):
        self.client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)

    def prefix_summary(self, bucket: str, prefix: str):
        count, size = 0, 0
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for o in page.get("Contents", []):
                count += 1
                size += o["Size"]
        return count, size

    def delete_prefix(self, bucket: str, prefix: str):
        if not prefix or not prefix.endswith("/"):
            raise ValueError(f"삭제할 접두어는 '/' 로 끝나야 합니다: {prefix!r}")
        keys = []
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            keys += [{"Key": o["Key"]} for o in page.get("Contents", [])]
        for i in range(0, len(keys), 1000):
            self.client.delete_objects(Bucket=bucket, Delete={"Objects": keys[i:i + 1000], "Quiet": True})
        # 끝나지 않은 나눠 올리기도 정리
        try:
            for page in self.client.get_paginator("list_multipart_uploads").paginate(Bucket=bucket, Prefix=prefix):
                for u in page.get("Uploads", []):
                    self.client.abort_multipart_upload(Bucket=bucket, Key=u["Key"], UploadId=u["UploadId"])
        except Exception as e:
            print(f"[S3] 끝나지 않은 나눠 올리기 정리 실패(무시): {e}")
        return len(keys)


s3_provider = S3Provider()
