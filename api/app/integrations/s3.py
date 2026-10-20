import boto3
from botocore.config import Config
from app.core.config import settings

class S3Provider:
    def __init__(self):
        self.client = boto3.client(
            's3',
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            endpoint_url=settings.MLFLOW_S3_ENDPOINT_URL,  # http://rustfs:9000
            region_name='us-east-1',
            # RustFS는 기본적으로 path-style 주소만 지원 (http://host/bucket/key)
            config=Config(s3={'addressing_style': 'path'}),
        )
    
    def list_buckets(self):
        response = self.client.list_buckets()
        return [b['Name'] for b in response.get('Buckets', [])]

    def browse_objects(self, bucket_name: str, prefix: str = ""):
        return self.client.list_objects_v2(
            Bucket=bucket_name, 
            Prefix=prefix, 
            Delimiter='/'
        )

s3_provider = S3Provider()