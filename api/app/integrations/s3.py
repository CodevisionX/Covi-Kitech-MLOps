import boto3
import os
from app.core.config import settings

class S3Provider:
    def __init__(self):
        self.client = boto3.client(
            's3',
            aws_access_key_id=settings.MINIO_ROOT_USER,       # MinIO ID를 Access Key로 매핑
            aws_secret_access_key=settings.MINIO_ROOT_PASSWORD, # MinIO PW를 Secret Key로 매핑
            endpoint_url=settings.MLFLOW_S3_ENDPOINT_URL,      # http://minio:9000
            region_name='us-east-1' # MinIO는 보통 기본값으로 이 값을 씁니다.
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