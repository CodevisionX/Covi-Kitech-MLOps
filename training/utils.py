import os
import boto3

def download_dataset(bucket_name, prefix, local_dir="/app/data"):
    """MinIO의 특정 폴더를 로컬로 재귀적으로 다운로드"""
    s3 = boto3.client('s3',
        endpoint_url=os.getenv('MLFLOW_S3_ENDPOINT_URL', "http://minio:9000"),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
    )

    if not os.path.exists(local_dir):
        os.makedirs(local_dir)

    print(f"📦 MinIO 다운로드 시작: {bucket_name}/{prefix} -> {local_dir}")
    
    paginator = s3.get_paginator('list_objects_v2')
    for result in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        if 'Contents' in result:
            for obj in result['Contents']:
                # 파일 경로 생성
                key = obj['Key']
                # 폴더 자체는 건너뜀
                if key.endswith('/'): continue
                
                local_file_path = os.path.join(local_dir, os.path.relpath(key, prefix))
                local_file_dir = os.path.dirname(local_file_path)
                
                if not os.path.exists(local_file_dir):
                    os.makedirs(local_file_dir)
                
                s3.download_file(bucket_name, key, local_file_path)
    
    print("✅ 데이터셋 다운로드 완료")
    return local_dir