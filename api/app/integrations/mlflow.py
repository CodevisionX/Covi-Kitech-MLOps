# MLflow Tracking 서버와의 통신을 전담
import mlflow
from mlflow.tracking import MlflowClient
from app.core.config import settings

class MlflowProvider:
    def __init__(self):
        self.tracking_uri = settings.MLFLOW_TRACKING_URI
        mlflow.set_tracking_uri(self.tracking_uri)
        self.client = MlflowClient()
    
    def create_run(self, experiment_id: str = None, experiment_name: str = None):
        target_exp_id = experiment_id

        if not target_exp_id and experiment_name:
            exp = mlflow.get_experiment_by_name(experiment_name)
            target_exp_id = exp.experiment_id if exp else mlflow.create_experiment(experiment_name)
        
        if not target_exp_id:
            target_exp_id = "0"
        
        return self.client.create_run(experiment_id=target_exp_id)

    def update_run_status(self, run_id: str, status: str):
        self.client.set_terminated(run_id, status=status)
    
    def get_run(self, run_id: str):
        return self.client.get_run(run_id)

    def register_model(self, run_id: str, model_name: str):
        """Run ID의 모델을 Registry에 등록하고 버전 정보를 반환합니다."""
        # 1. 먼저 해당 Run의 상세 정보를 가져와서 artifact_uri(기본 경로)를 확인합니다.
        run = self.client.get_run(run_id)
        artifact_uri = run.info.artifact_uri  # 예: s3://mlflow-artifacts/1/run_id/artifacts
        
        # 2. 실제 best.pt가 있는 'weights' 폴더까지의 절대 경로를 만듭니다.
        # 사용자님의 경로 구조에 맞게 'weights'를 뒤에 붙입니다.
        model_uri = f"{artifact_uri}/model" 
        
        print(f"[MlflowProvider] Final Model URI for registration: {model_uri}")
        
        # 3. 절대 경로를 이용해 모델 등록
        result = mlflow.register_model(model_uri, model_name)
        return result.version

mlflow_provider = MlflowProvider()