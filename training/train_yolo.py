import os
import mlflow
from ultralytics import YOLO, settings
from utils import download_dataset # 위 유틸리티 임포트

def train_yolo():
    # 1. 환경 변수 및 경로 설정
    run_id = os.getenv("MLFLOW_RUN_ID")
    raw_path = os.getenv("DATASET_PATH") 
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    
    if not run_id:
        print("❌ MLFLOW_RUN_ID가 설정되지 않았습니다.")
        return
    
    # 2. Ultralytics 기본 MLflow 로깅 비활성화 (수동 로깅을 위해)
    # YOLO가 스스로 새 Run을 만드는 것을 방지합니다.
    settings.update({"mlflow": False})

    # 3. 데이터 다운로드
    try:
        bucket, prefix = raw_path.split('/', 1)
        local_data_path = download_dataset(bucket, prefix)
    except Exception as e:
        print(f"❌ 데이터 다운로드 실패: {e}")
        return

    # 4. MLflow 설정 및 실행 (서버에서 만든 run_id를 이어받음)
    mlflow.set_tracking_uri(tracking_uri)

    # run_id를 지정하여 start_run을 호출하면, 서버에서 만든 RUNNING 상태의 런을 이어받습니다.
    with mlflow.start_run(run_id=run_id):
        try:
            print(f"🚀 학습 시작 (Run ID: {run_id})")
            
            # 모델 로드
            model_variant = os.getenv("MODEL_VARIANT", "yolov8n.pt")
            model = YOLO(model_variant)
            
            # 하이퍼파라미터 로깅
            epochs = int(os.getenv("EPOCHS", 10))
            batch = int(os.getenv("BATCH", 16))
            mlflow.log_params({
                "epochs": epochs,
                "batch": batch,
                "model_variant": model_variant,
                "dataset": raw_path
            })

            # 5. 모델 학습
            results = model.train(
                data=os.path.join(local_data_path, "data.yaml"),
                epochs=epochs,
                batch=batch,
                device=0,
                project='/app/runs',
                name='exp',
                plots=True # 결과 차트 생성
            )

            # 6. 결과 지표(Metrics) 로깅
            # YOLO 학습 결과에서 최종 메트릭을 추출하여 기록합니다.
            if hasattr(results, 'results_dict'):
                mlflow.log_metrics(results.results_dict)

            # 7. Artifact 업로드 (가중치 파일)
            best_pt = os.path.join(results.save_dir, "weights", "best.pt")
            if os.path.exists(best_pt):
                mlflow.log_artifact(best_pt, artifact_path="model/weights")
                print(f"✅ 모델 저장 완료: {best_pt}")

            print("🏁 학습이 성공적으로 종료되었습니다.")

        except Exception as e:
            # 학습 도중 에러 발생 시 상태를 FAILED로 기록하도록 예외 처리
            print(f"❌ 학습 중 에러 발생: {e}")
            traceback.print_exc()
            # with 블록을 나가면서 자동으로 상태가 업데이트되지만, 
            # 명시적으로 에러를 다시 발생시켜 MLflow에 알릴 수 있습니다.
            raise e

if __name__ == "__main__":
    train_yolo()