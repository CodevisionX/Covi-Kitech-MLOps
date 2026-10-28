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
        # MLflow 3 부터 log_model 결과는 run 아티팩트 폴더가 아닌 별도 위치(LoggedModel)에
        # 저장되므로 S3 경로를 직접 만들지 않고 runs:/ URI 로 등록합니다(2.x 와도 호환).
        model_uri = f"runs:/{run_id}/model"

        print(f"[MlflowProvider] Final Model URI for registration: {model_uri}")

        result = mlflow.register_model(model_uri, model_name)
        return result.version

mlflow_provider = MlflowProvider()