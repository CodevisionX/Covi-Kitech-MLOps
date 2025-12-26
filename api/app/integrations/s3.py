import boto3
import os
from app.core.config import settings

class S3Provider:
    def __init__(self):
        self.client = boto3.client(
            's3',
            endpoint_url=os.getenv('MLFLOW_S3_ENDPOINT_URL', "http://minio:9000"),
            minio_root_user=os.getenv('MINIO_ROOT_USER', "minio"),
            minio_root_password=os.getenv('MINIO_ROOT_PASSWORD', "minio123")
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