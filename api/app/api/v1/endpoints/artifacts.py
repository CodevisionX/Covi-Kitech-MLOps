# 데이터셋 브라우징 (S3 연동)
from fastapi import APIRouter, HTTPException, Query
from app.integrations.s3 import s3_provider
from app.schemas.artifact import DatasetListResponse, BrowseResponse, S3FileResponse

router = APIRouter()

@router.get("/datasets", response_model=DatasetListResponse)
async def list_datasets():
    """S3 버킷 목록을 데이터셋 단위로 조회합니다."""
    try:
        buckets = s3_provider.list_buckets()
        return DatasetListResponse(datasets=buckets)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/browse/{bucket_name}", response_model=BrowseResponse)
async def browse_dataset(bucket_name: str, prefix: str = Query("")):
    """특정 버킷 내부의 파일 및 폴더 구조를 탐색합니다."""
    try:
        response = s3_provider.browse_objects(bucket_name, prefix)
        
        folders = [p['Prefix'] for p in response.get('CommonPrefixes', [])]
        files = [
            S3FileResponse(
                name=obj['Key'].split('/')[-1],
                full_path=obj['Key'],
                size=obj['Size']
            ) for obj in response.get('Contents', []) if obj['Key'] != prefix
        ]
        
        return BrowseResponse(
            current_path=prefix,
            folders=folders,
            files=files
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))