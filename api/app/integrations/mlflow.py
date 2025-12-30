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
    
mlflow_provider = MlflowProvider()