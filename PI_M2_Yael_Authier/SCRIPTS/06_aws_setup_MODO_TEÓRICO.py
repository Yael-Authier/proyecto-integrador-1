# import boto3  # <- No se usa aquí. Este archivo es solo de diseño/plan.

"""
06_aws_setup.py — MODO TEÓRICO (no crea recursos)
Propósito: documentar el plan de infraestructura y generar un aws_config.json de ejemplo.
"""
# import boto3  # <- No se usa aquí. Este archivo es solo de diseño/plan.
import json
import re
from datetime import datetime, timezone

# ---------------------------
# 0) Parámetros de diseño
# ---------------------------
# SIRVEN para definir convenciones de nombres y el “molde” de la infraestructura.
REGION = "us-east-1"
PROJECT = "fleetlogix"
ENV = "dev"

S3_BUCKET = f"{PROJECT}-{ENV}-data".lower()  # nombre teórico de bucket
RDS_INSTANCE_ID = f"{PROJECT}-{ENV}-rds-postgres"  # instancia RDS teórica
RDS_DB_NAME = "fleetlogix_dw"  # nombre de DB en RDS
IAM_ROLE_NAME = f"{PROJECT}-{ENV}-lambda-role"  # rol teórico para Lambdas
SNS_TOPIC_NAME = f"{PROJECT}-{ENV}-alerts"  # tópico de alertas

# ---------------------------
# 1) Estructuras lógicas
# ---------------------------
# Aclaran cómo se guardaría la info sin crear nada realmente.
S3_PREFIXES = ["raw-data/", "processed-data/", "backups/", "logs/"]

DDB_TABLES = {
    # nombre_tabla: {clave_primaria, modo_facturación}
    "deliveries_status": {"pk": "delivery_id", "billing": "on-demand"},
    "vehicle_tracking": {"pk": "vehicle_id", "billing": "on-demand"},
    "routes_waypoints": {"pk": "route_id", "billing": "on-demand"},
    "alerts_history": {"pk": "alert_id", "billing": "on-demand"},
}

# ---------------------------
# 2) Validadores simples
# ---------------------------
# Sirven para chequear que los nombres cumplen reglas básicas (ej., S3).
def is_valid_s3_bucket(name: str) -> bool:
    return (
        3 <= len(name) <= 63
        and re.match(r"^[a-z0-9.-]+$", name) is not None
        and not name.startswith(".")
        and not name.endswith(".")
        and ".." not in name
    )

# ---------------------------
# 3) “Plan de despliegue” (solo imprime)
# ---------------------------
def print_plan():
    print("== Plan de Infraestructura (Simulación) ==")
    print(f"Región objetivo: {REGION}\n")

    print(f"Validando nombre S3: {S3_BUCKET}")
    assert is_valid_s3_bucket(S3_BUCKET), "Nombre de bucket no válido."
    print("OK.\n")

    print("Estructura S3 propuesta:")
    for p in S3_PREFIXES:
        print(f"  - s3://{S3_BUCKET}/{p}")
    print("\nSugerencia: lifecycle → raw-data/ a Glacier a los 90 días.\n")

    print("Tablas DynamoDB (teóricas):")
    for t, meta in DDB_TABLES.items():
        print(f"  - {t}  (PK: {meta['pk']}, billing: {meta['billing']})")
    print()

    print(f"IAM Role (Lambdas): {IAM_ROLE_NAME}")
    print("Políticas mínimas sugeridas: acceso granular a S3, DynamoDB y SNS.")
    print(f"SNS Topic (alertas): {SNS_TOPIC_NAME}\n")

    print(f"RDS PostgreSQL (teórico): {RDS_INSTANCE_ID} | DB: {RDS_DB_NAME}")
    print("Backups automáticos: habilitados (teórico).\n")

# ---------------------------
# 4) Artefacto ejemplo
# ---------------------------
# Genera un JSON simulado que “documenta” la arquitectura.
def write_example_config():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cfg = {
        "generated_at_utc": now,
        "region": REGION,
        "s3": {"bucket": S3_BUCKET, "prefixes": S3_PREFIXES, "lifecycle_raw_to_glacier_days": 90},
        "dynamodb": {
            "tables": [{"name": t, "pk": m["pk"], "billing": m["billing"]} for t, m in DDB_TABLES.items()]
        },
        "iam": {"lambda_role": IAM_ROLE_NAME, "policies_sugeridas": ["S3", "DynamoDB", "SNS (mínimo privilegio)"]},
        "sns": {
            "topic_name": SNS_TOPIC_NAME,
            "topic_arn_example": f"arn:aws:sns:{REGION}:123456789012:{SNS_TOPIC_NAME}"
        },
        "rds": {"engine": "postgres", "instance_id": RDS_INSTANCE_ID, "db_name": RDS_DB_NAME, "backup_automatico": True},
    }
    with open("aws_config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ---------------------------
# 5) Checklist (guía de despliegue real)
# ---------------------------
def print_checklist():
    print("Checklist (si fuese despliegue real):")
    print("  [ ] Crear bucket S3 + lifecycle")
    print("  [ ] Crear tablas DynamoDB (4) con PK y on-demand")
    print("  [ ] IAM role para Lambda con mínimo privilegio")
    print("  [ ] SNS Topic y suscripciones (email/SQS)")
    print("  [ ] RDS PostgreSQL con backups automáticos")
    print("  [ ] 3 Lambdas y API Gateway (POST)")
    print("  [ ] CORS + Deploy de API")
    print("  [ ] Pruebas con curl/Postman\n")
    print("Nota: este script NO crea recursos; documenta el plan.")

# ---------------------------
# 6) Main teórico
# ---------------------------
def main():
    print_plan()
    write_example_config()
    print_checklist()

if __name__ == "__main__":
    main()
