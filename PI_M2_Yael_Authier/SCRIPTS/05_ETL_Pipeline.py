#### PIPELINE ETL - FLEETLOGIX DATA WAREHOUSE
#### Avance 3: Migración de Datos PostgreSQL → Snowflake
# Objetivo: Desarrollar un pipeline ETL completo que:
#  - Extraiga datos de la base transaccional PostgreSQL,
#  - Los transforme según el modelo estrella
#  - Y los cargue en el Data Warehouse de Snowflake.
# Estado: Modelo estrella implementado en Snowflake, listo para carga de datos.


# =======================
# 0.1) IMPORTAMOS LIBRERÍAS
# =======================
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from snowflake.connector import connect as sf_connect
from snowflake.connector.pandas_tools import write_pandas
from snowflake.connector.errors import MissingDependencyError


# =======================
# 0.2) LOGGING
# =======================
logging.basicConfig(
    filename="etl_last_week.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# =======================
# 0.3) CONFIGURACIÓN
# =======================
pg_config = {
    'host': 'localhost',
    'database': 'fleetlogix',        # Base de datos local
    'user': 'fleetlogix_user',
    'password': 'fleetlogix123',
    'port': '5432'
}

sf_config = {
    'user': 'YaelAuthier',
    'password': 'Y4uthier4uthier1639',
    'account': 'RRFGSWD-LT49554',
    'warehouse': 'COMPUTE_WH',
    'database': 'FLEETLOGIX_DW',
    'schema': 'BI_SCHEMA'
}

WINDOW_DAYS = 7  # Últimos N días a cargar


# =======================
# 1) CONEXIONES: creamos conexiones (SQLAlchemy para Postgres y Snowflake Connector).
# =======================
def connect_postgres(cfg: dict):
    """Establece conexión con PostgreSQL mediante SQLAlchemy."""
    dsn = f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    engine = create_engine(dsn, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logging.info("PostgreSQL OK")
    return engine.connect()


def connect_snowflake(cfg: dict):
    """Establece conexión con Snowflake."""
    con = sf_connect(
        user=cfg['user'],
        password=cfg['password'],
        account=cfg['account'],
        warehouse=cfg['warehouse'],
        database=cfg['database'],
        schema=cfg['schema']
    )
    con.cursor().execute("SELECT 1")
    logging.info("Snowflake OK")
    return con


# =======================
# 2) EXTRACT: trae últimos 7 días de trips y deliveries, y tablas maestras (drivers, vehicles, routes).
# =======================
def extract_last_week(pg, window_days):
    """Extrae viajes y entregas de la última semana disponible."""
    anchor_query = "SELECT MAX(delivered_datetime) FROM deliveries;"
    anchor = pd.read_sql(anchor_query, pg).iloc[0, 0]
    since = anchor - timedelta(days=window_days)
    logging.info(f"Extrayendo datos relativos al ancla={anchor} (últimos {window_days} días) -> since={since}")

    trips = pd.read_sql(
        f"SELECT * FROM trips WHERE departure_datetime >= '{since}'", pg)
    deliveries = pd.read_sql(
        f"SELECT * FROM deliveries WHERE delivered_datetime >= '{since}'", pg)
    drivers = pd.read_sql("SELECT * FROM drivers", pg)
    vehicles = pd.read_sql("SELECT * FROM vehicles", pg)
    routes = pd.read_sql("SELECT * FROM routes", pg)

    logging.info(f"Extract OK (dinámico): trips={len(trips)} deliveries={len(deliveries)}")
    return trips, deliveries, drivers, vehicles, routes


# =======================
# 3) TRANSFORM: construye dimensiones y el hecho fact_ con sus métricas
# =======================

def build_dims_and_fact_stg(trips, deliveries, drivers, vehicles, routes):
    """Construye dimensiones y tabla de hechos staging."""

    # DIM_DATE
    all_dates = pd.to_datetime(deliveries["delivered_datetime"].dropna().dt.date.unique())
    dim_date = pd.DataFrame({
        "date_key": all_dates.strftime("%Y%m%d").astype(int),
        "full_date": all_dates,
        "day_of_week": all_dates.dayofweek,
        "day_name": all_dates.strftime("%A"),
        "month_num": all_dates.month,
        "year": all_dates.year
    })

    # DIM_TIME
    def hhmm(dt): return int(pd.Timestamp(dt).strftime("%H%M"))
    dim_time = pd.DataFrame({
        "time_key": sorted({
            *[hhmm(x) for x in deliveries["scheduled_datetime"].dropna()],
            *[hhmm(x) for x in deliveries["delivered_datetime"].dropna()]
        })
    })

    # DIM_DRIVER
    dim_driver = drivers.copy()
    dim_driver["driver_key"] = dim_driver["driver_id"]
    dim_driver["experience_months"] = (
        (datetime.now() - pd.to_datetime(dim_driver["hire_date"])).dt.days // 30
    )

    # DIM_VEHICLE
    dim_vehicle = vehicles.copy()
    dim_vehicle["vehicle_key"] = dim_vehicle["vehicle_id"]

    # DIM_ROUTE
    dim_route = routes.copy()
    dim_route["route_key"] = dim_route["route_id"]

    # DIM_CUSTOMER
    # Creamos la dimensión de clientes usando lo que exista en deliveries
    possible_cols = [c for c in deliveries.columns if c.lower() in ["customer_id", "client_id", "recipient_id", "customer_name"]]
    if not possible_cols:
        logging.warning("No se encontró columna de cliente en deliveries.")
        dim_customer = pd.DataFrame(columns=[
            "customer_key", "customer_name", "customer_type", "city",
            "first_delivery_date", "total_deliveries", "customer_category"
        ])
    else:
        key_col = possible_cols[0]
        dim_customer = deliveries[[key_col]].drop_duplicates().reset_index(drop=True)
        dim_customer.rename(columns={key_col: "customer_name"}, inplace=True)
        dim_customer["customer_key"] = dim_customer.index + 1
        dim_customer["customer_type"] = np.random.choice(["Individual", "Empresa", "Gobierno"], size=len(dim_customer))
        dim_customer["city"] = np.random.choice(
            ["Buenos Aires", "Córdoba", "Rosario", "Mendoza", "La Plata"], size=len(dim_customer)
        )

        # Métricas de entregas
        first_dates = deliveries.groupby(key_col)["delivered_datetime"].min().reset_index()
        first_dates.columns = ["customer_name", "first_delivery_date"]

        total_del = deliveries.groupby(key_col)["delivery_id"].count().reset_index()
        total_del.columns = ["customer_name", "total_deliveries"]

        dim_customer = dim_customer.merge(first_dates, on="customer_name", how="left")
        dim_customer = dim_customer.merge(total_del, on="customer_name", how="left")

        dim_customer["customer_category"] = np.where(
            dim_customer["total_deliveries"] > 50, "Premium",
            np.where(dim_customer["total_deliveries"] > 10, "Regular", "Ocasional")
        )

    # FACT STG
    fact_stg = deliveries.merge(trips, on="trip_id", suffixes=("_del", "_trip"))
    fact_stg["date_key"] = fact_stg["delivered_datetime"].dt.strftime("%Y%m%d").astype(int)
    fact_stg["scheduled_time_key"] = fact_stg["scheduled_datetime"].dt.strftime("%H%M").astype(int)
    fact_stg["delivered_time_key"] = fact_stg["delivered_datetime"].dt.strftime("%H%M").astype(int)

    # Asignar CUSTOMER_KEY de forma flexible
    possible_keys = ["customer_id", "client_id", "recipient_id", "customer_name"]
    existing_keys = [col for col in fact_stg.columns if col in possible_keys]

    if existing_keys:
        key_col = existing_keys[0]
        logging.info(f"Fact_stg: usando '{key_col}' para asignar CUSTOMER_KEY.")
        if key_col == "customer_name":
            fact_stg = fact_stg.merge(
                dim_customer[["customer_name", "customer_key"]],
                on="customer_name", how="left"
            )
        else:
            fact_stg = fact_stg.merge(
                dim_customer[["customer_name", "customer_key"]],
                left_on=key_col, right_on="customer_name", how="left"
            )
        logging.info("Fact_stg: CUSTOMER_KEY completado mediante merge con DIM_CUSTOMER.")
    else:
        logging.warning("No se encontró columna de cliente en fact_stg (CUSTOMER_KEY quedó vacío).")

    return dim_date, dim_time, dim_driver, dim_vehicle, dim_route, dim_customer, fact_stg

# =======================
# 4) VALIDACIONES: claves no nulas en fact y que la duración no sea negativa.
# =======================
def validate_fact_stg(fact_stg):
    """Verifica integridad básica."""
    assert fact_stg["delivered_datetime"].notnull().all(), "Hay entregas sin fecha de entrega"
    assert (fact_stg["delivered_datetime"] >= fact_stg["scheduled_datetime"]).all(), "Fechas inconsistentes"
    logging.info("Validaciones OK")

# =======================
# 5.1)CARGA AUXILIAR
# =======================
def get_existing_keys(con, table, key_col):
    try:
        cur = con.cursor()
        cur.execute(f"SELECT {key_col} FROM {table};")
        return [r[0] for r in cur.fetchall()]
    except Exception:
        return []


def _batch_insert(con, table, df):
    """Carga alternativa por lotes si write_pandas falla."""
    if df.empty:
        return 0
    df2 = df.copy()
    df2.columns = [c.upper() for c in df2.columns]
    df2 = df2.where(pd.notnull(df2), None)
    cols = list(df2.columns)
    placeholders = ",".join(["%s"] * len(cols))
    sql = f'INSERT INTO {table} ({",".join(cols)}) VALUES ({placeholders})'
    rows = [tuple(x) for x in df2.itertuples(index=False, name=None)]
    cur = con.cursor()
    try:
        cur.executemany(sql, rows)
    finally:
        cur.close()
    return len(rows)


def write_dim(con, table, df, key_col):
    """Carga una dimensión en Snowflake."""
    if df.empty:
        return 0

    existing = get_existing_keys(con, table, key_col)
    df2 = df[~df[key_col].isin(existing)].copy()
    if df2.empty:
        logging.info(f"{table}: 0 filas nuevas")
        return 0

    for col in df2.select_dtypes(include=["datetime64[ns]"]).columns:
        df2[col] = df2[col].dt.date

    try:
        df3 = df2.copy()
        df3.columns = [c.upper() for c in df3.columns]
        ok, _, nrows, _ = write_pandas(con, df3, table, quote_identifiers=False)
        if not ok:
            raise Exception(f"Falla al cargar {table} con write_pandas")
        logging.info(f"{table}: {nrows} filas nuevas (write_pandas)")
        return nrows

    except MissingDependencyError:
        nrows = _batch_insert(con, table, df2)
        logging.info(f"{table}: {nrows} filas nuevas (fallback executemany)")
        return nrows


# =======================
# 5.2) CARGA FINAL (FACT)
# =======================
def write_fact_stg_and_insert_final(con, fact_stg):
    """Carga staging y luego inserta en FACT_DELIVERIES final."""
    if fact_stg.empty:
        logging.info("FACT_DELIVERIES_STG: 0 filas (sin datos nuevos)")
        return

    # Renombrar columnas para coincidir con Snowflake
    rename_map = {
        "vehicle_id": "vehicle_key",
        "driver_id": "driver_key",
        "route_id": "route_key",
        "customer_id": "customer_key",
        "trip_id": "trip_id",
        "delivery_id": "delivery_id"
    }
    fact_stg = fact_stg.rename(columns=rename_map)

    # Eliminar columnas no esperadas por Snowflake (como customer_name)
    columnas_permitidas = [
        "date_key", "scheduled_time_key", "delivered_time_key",
        "vehicle_key", "driver_key", "route_key", "customer_key",
        "delivery_id", "trip_id", "tracking_number",
        "package_weight_kg", "distance_km", "fuel_consumed_liters",
        "delivery_time_minutes", "delay_minutes",
        "deliveries_per_hour", "fuel_efficiency_km_per_liter",
        "cost_per_delivery", "revenue_per_delivery",
        "is_on_time", "is_damaged", "has_signature", "delivery_status"
    ]

    fact_stg = fact_stg[[c for c in fact_stg.columns if c in columnas_permitidas]]

    # Asegurar tipos correctos para fechas
    for col in fact_stg.select_dtypes(include=["datetime64[ns]"]).columns:
        fact_stg[col] = fact_stg[col].dt.strftime("%Y-%m-%d %H:%M:%S")

    df2 = fact_stg.copy()
    df2.columns = [c.upper() for c in df2.columns]

    try:
        ok, _, nrows, _ = write_pandas(con, df2, "FACT_DELIVERIES_STG", quote_identifiers=False)
        if not ok:
            raise Exception("Falla al cargar FACT_DELIVERIES_STG con write_pandas")
        logging.info(f"FACT_DELIVERIES_STG: {nrows} filas insertadas (write_pandas)")
    except MissingDependencyError:
        nrows = _batch_insert(con, "FACT_DELIVERIES_STG", fact_stg)
        logging.info(f"FACT_DELIVERIES_STG: {nrows} filas insertadas (fallback executemany)")

    # Insertar en la tabla final
    cur = con.cursor()
    try:
        sql_insert = """
            INSERT INTO FACT_DELIVERIES (
                DATE_KEY, SCHEDULED_TIME_KEY, DELIVERED_TIME_KEY,
                VEHICLE_KEY, DRIVER_KEY, ROUTE_KEY, CUSTOMER_KEY,
                DELIVERY_ID, TRIP_ID, TRACKING_NUMBER,
                PACKAGE_WEIGHT_KG, DISTANCE_KM, FUEL_CONSUMED_LITERS,
                DELIVERY_TIME_MINUTES, DELAY_MINUTES,
                DELIVERIES_PER_HOUR, FUEL_EFFICIENCY_KM_PER_LITER,
                COST_PER_DELIVERY, REVENUE_PER_DELIVERY,
                IS_ON_TIME, IS_DAMAGED, HAS_SIGNATURE, DELIVERY_STATUS
            )
            SELECT
                DATE_KEY, SCHEDULED_TIME_KEY, DELIVERED_TIME_KEY,
                VEHICLE_KEY, DRIVER_KEY, ROUTE_KEY, CUSTOMER_KEY,
                DELIVERY_ID, TRIP_ID, TRACKING_NUMBER,
                PACKAGE_WEIGHT_KG, DISTANCE_KM, FUEL_CONSUMED_LITERS,
                DELIVERY_TIME_MINUTES, DELAY_MINUTES,
                DELIVERIES_PER_HOUR, FUEL_EFFICIENCY_KM_PER_LITER,
                COST_PER_DELIVERY, REVENUE_PER_DELIVERY,
                IS_ON_TIME, IS_DAMAGED, HAS_SIGNATURE, DELIVERY_STATUS
            FROM FACT_DELIVERIES_STG;
        """
        cur.execute(sql_insert)
        logging.info("FACT_DELIVERIES: insert final OK")
    finally:
        cur.close()

# =======================
# 6) MAIN: orquesta todo y deja logs en etl_last_week.log
# =======================
def main():
    logging.info("== ETL FleetLogix (última semana, ventana dinámica, sin tz) ==")
    pg = connect_postgres(pg_config)
    sf = connect_snowflake(sf_config)

    trips, deliveries, drivers, vehicles, routes = extract_last_week(pg, WINDOW_DAYS)
    dim_date, dim_time, dim_driver, dim_vehicle, dim_route, dim_customer, fact_stg = build_dims_and_fact_stg(
        trips, deliveries, drivers, vehicles, routes
    )
    validate_fact_stg(fact_stg)

    # Normalizar columnas de driver
    if "first_name" in dim_driver.columns and "last_name" in dim_driver.columns:
        dim_driver["full_name"] = dim_driver["first_name"].str.strip() + " " + dim_driver["last_name"].str.strip()
        dim_driver.drop(columns=["first_name", "last_name"], inplace=True, errors="ignore")
        logging.info("dim_driver: columnas normalizadas (full_name creado).")

    total = 0
    total += write_dim(sf, "DIM_DATE", dim_date, "date_key")
    total += write_dim(sf, "DIM_TIME", dim_time, "time_key")
    total += write_dim(sf, "DIM_DRIVER", dim_driver, "driver_key")
    total += write_dim(sf, "DIM_VEHICLE", dim_vehicle, "vehicle_key")
    total += write_dim(sf, "DIM_ROUTE", dim_route, "route_key")
    total += write_dim(sf, "DIM_CUSTOMER", dim_customer, "customer_key")

    write_fact_stg_and_insert_final(sf, fact_stg)

    logging.info(f"ETL completado. Filas nuevas (dims+fact_stg): {total + len(fact_stg)}")
    sf.close()


if __name__ == "__main__":
    main()