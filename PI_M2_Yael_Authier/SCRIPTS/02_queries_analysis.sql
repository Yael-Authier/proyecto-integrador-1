-- =====================================================
-- FLEETLOGIX - ANÁLISIS COMPLETO DE QUERIES
-- Avance 2 - Análisis de Performance (ANTES y DESPUÉS)
-- =====================================================

-- QUERY 1: Contar vehículos por tipo
-- Problema de negocio: Composición de la flota vehicular
-- Tiempo ANTES: 0.020s | DESPUÉS: 0.004s | MEJORA: 80%

SELECT 
    vehicle_type,
    COUNT(*) as cantidad
FROM vehicles
GROUP BY vehicle_type
ORDER BY cantidad DESC;

-- QUERY 2: Conductores con licencia próxima a vencer  
-- Problema de negocio: Prevención de problemas legales
-- Tiempo ANTES: 0.017s | DESPUÉS: 0.005s | MEJORA: 71%

SELECT 
    first_name,
    last_name,
    license_number,
    license_expiry
FROM drivers
WHERE license_expiry < CURRENT_DATE + INTERVAL '30 days'
ORDER BY license_expiry;

-- QUERY 3: Total de viajes por estado
-- Problema de negocio: Monitoreo de operaciones
-- Tiempo ANTES: 0.057s | DESPUÉS: 0.025s | MEJORA: 56%

SELECT 
    status,
    COUNT(*) as total_viajes
FROM trips
GROUP BY status;

-- QUERY 4: Entregas por ciudad destino (últimos 60 días)
-- Problema de negocio: Planificación de recursos por ciudad
-- Tiempo ANTES: 0.121s | DESPUÉS: 0.103s | MEJORA: 15%

SELECT 
    r.destination_city,
    COUNT(DISTINCT t.trip_id) as total_viajes,
    COUNT(d.delivery_id) as total_entregas,
    SUM(d.package_weight_kg) as peso_total_kg
FROM routes r
INNER JOIN trips t ON r.route_id = t.route_id
INNER JOIN deliveries d ON t.trip_id = d.trip_id
WHERE t.departure_datetime >= CURRENT_DATE - INTERVAL '60 days'
GROUP BY r.destination_city
ORDER BY total_entregas DESC;

-- QUERY 5: Conductores activos con cantidad de viajes
-- Problema de negocio: Evaluar carga de trabajo por conductor
-- Tiempo ANTES: 0.049s | DESPUÉS: 0.047s | MEJORA: 4%

SELECT 
    d.driver_id,
    d.first_name || ' ' || d.last_name as nombre_completo,
    d.license_expiry,
    COUNT(t.trip_id) as viajes_totales,
    SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as viajes_completados
FROM drivers d
LEFT JOIN trips t ON d.driver_id = t.driver_id
WHERE d.status = 'active'
GROUP BY d.driver_id, d.first_name, d.last_name, d.license_expiry
HAVING COUNT(t.trip_id) > 0
ORDER BY viajes_completados DESC;

-- QUERY 6: Promedio de entregas por conductor (últimos 6 meses)
-- Problema de negocio: Medir productividad de conductores
-- Tiempo ANTES: 0.215s | DESPUÉS: 0.174s | MEJORA: 19%

SELECT 
    dr.driver_id,
    dr.first_name || ' ' || dr.last_name as conductor,
    COUNT(DISTINCT t.trip_id) as total_viajes,
    COUNT(d.delivery_id) as total_entregas,
    ROUND(COUNT(d.delivery_id)::NUMERIC / NULLIF(COUNT(DISTINCT t.trip_id), 0), 2) as promedio_entregas_por_viaje,
    ROUND(COUNT(d.delivery_id)::NUMERIC / 180, 2) as promedio_entregas_diarias
FROM drivers dr
INNER JOIN trips t ON dr.driver_id = t.driver_id
INNER JOIN deliveries d ON t.trip_id = d.trip_id
WHERE t.departure_datetime >= CURRENT_DATE - INTERVAL '6 months'
    AND t.status = 'completed'
GROUP BY dr.driver_id, dr.first_name, dr.last_name
HAVING COUNT(DISTINCT t.trip_id) >= 10
ORDER BY promedio_entregas_por_viaje DESC;

-- QUERY 9: Costo de mantenimiento por kilómetro recorrido
-- Problema de negocio: Evaluar costo-beneficio por tipo de vehículo
-- Tiempo ANTES: 0.919s | DESPUÉS: 0.877s | MEJORA: 5%

WITH vehicle_metrics AS (
    SELECT 
        v.vehicle_id,
        v.vehicle_type,
        v.license_plate,
        COUNT(DISTINCT t.trip_id) as total_viajes,
        SUM(r.distance_km) as km_totales,
        SUM(m.cost) as costo_mantenimiento_total,
        COUNT(DISTINCT m.maintenance_id) as cantidad_mantenimientos
    FROM vehicles v
    LEFT JOIN trips t ON v.vehicle_id = t.vehicle_id
    LEFT JOIN routes r ON t.route_id = r.route_id
    LEFT JOIN maintenance m ON v.vehicle_id = m.vehicle_id
    WHERE t.status = 'completed'
    GROUP BY v.vehicle_id, v.vehicle_type, v.license_plate
)
SELECT 
    vehicle_type,
    COUNT(vehicle_id) as cantidad_vehiculos,
    SUM(total_viajes) as viajes_totales,
    SUM(km_totales) as kilometros_totales,
    SUM(costo_mantenimiento_total) as costo_total_mantenimiento,
    ROUND(SUM(costo_mantenimiento_total) / NULLIF(SUM(km_totales), 0), 2) as costo_por_km,
    ROUND(AVG(costo_mantenimiento_total / NULLIF(cantidad_mantenimientos, 0)), 2) as costo_promedio_por_mantenimiento
FROM vehicle_metrics
WHERE km_totales > 0 AND costo_mantenimiento_total > 0
GROUP BY vehicle_type
ORDER BY costo_por_km DESC;

-- QUERY 11: Análisis de tendencia de viajes con LAG y LEAD
-- Problema de negocio: Proyección de necesidades futuras
-- Tiempo ANTES: 0.045s | DESPUÉS: 0.042s | MEJORA: 7%

WITH viajes_mensuales AS (
    SELECT 
        DATE_TRUNC('month', departure_datetime) as mes,
        COUNT(*) as total_viajes,
        SUM(total_weight_kg) as peso_total,
        AVG(fuel_consumed_liters) as combustible_promedio
    FROM trips
    WHERE status = 'completed'
    GROUP BY DATE_TRUNC('month', departure_datetime)
)
SELECT 
    TO_CHAR(mes, 'YYYY-MM') as periodo,
    total_viajes,
    LAG(total_viajes, 1) OVER (ORDER BY mes) as viajes_mes_anterior,
    LEAD(total_viajes, 1) OVER (ORDER BY mes) as viajes_mes_siguiente,
    total_viajes - LAG(total_viajes, 1) OVER (ORDER BY mes) as cambio_absoluto,
    ROUND((total_viajes - LAG(total_viajes, 1) OVER (ORDER BY mes))::NUMERIC / 
          NULLIF(LAG(total_viajes, 1) OVER (ORDER BY mes), 0) * 100, 2) as cambio_porcentual,
    ROUND(peso_total / 1000, 2) as toneladas_transportadas,
    ROUND(combustible_promedio, 2) as combustible_promedio_viaje,
    AVG(total_viajes) OVER (ORDER BY mes ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) as promedio_movil_3m
FROM viajes_mensuales
ORDER BY mes DESC
LIMIT 12;

--- SUMAMOS ALGUNAS QUERY ADICIONALES
-- NEW QUERY 1: Entregas tardías por conductor (últimos 90 días)
-- Problema de negocio: Monitoreo del desempeño de conductores y cumplimiento de tiempos de entrega
-- Tiempo ANTES: 0.192s | DESPUÉS: 0.114s | MEJORA: 41%
WITH base AS (
  SELECT d.driver_id, del.delivery_id,
         del.scheduled_datetime, del.delivered_datetime
  FROM trips t
  JOIN deliveries del ON del.trip_id = t.trip_id
  JOIN drivers d       ON d.driver_id = t.driver_id
  WHERE del.delivery_status <> 'pending'
    AND t.departure_datetime >= NOW() - INTERVAL '90 days'
)
SELECT driver_id,
       COUNT(*)                          AS entregas,
       SUM((delivered_datetime > scheduled_datetime)::int) AS tardias,
       ROUND(100.0 * SUM((delivered_datetime > scheduled_datetime)::int) / COUNT(*), 2) AS porc_tardias
FROM base
GROUP BY driver_id
ORDER BY porc_tardias DESC, entregas DESC
LIMIT 50;

--NEW QUERY 2: Utilización de capacidad por vehículo (últimos 60 días)
-- Problema de negocio: Optimización de recursos y planificación de flota vehicular
-- Tiempo ANTES: 0.023s | DESPUÉS: 0.0009s | MEJORA: 96%


SELECT v.vehicle_id, v.vehicle_type,
       ROUND(AVG(t.total_weight_kg / NULLIF(v.capacity_kg,0)),3) AS avg_utilizacion
FROM trips t
JOIN vehicles v ON v.vehicle_id = t.vehicle_id
WHERE t.departure_datetime >= NOW() - INTERVAL '60 days'
  AND t.status = 'completed'
GROUP BY v.vehicle_id, v.vehicle_type
ORDER BY avg_utilizacion DESC;

-- NEW QUERY 3:Top 10 rutas por costo de peaje efectivo por entrega (últimos 30 días)
-- Problema de negocio: Análisis de costos operativos y eficiencia en gestión de rutas
-- Tiempo ANTES: 0.099s | DESPUÉS: 0.037s | MEJORA: 63%
WITH rtd AS (
  SELECT t.route_id,
         COUNT(del.delivery_id) AS entregas,
         SUM(r.toll_cost)       AS peaje_total
  FROM trips t
  JOIN routes r     ON r.route_id = t.route_id
  JOIN deliveries del ON del.trip_id = t.trip_id
  WHERE t.departure_datetime >= NOW() - INTERVAL '30 days'
    AND t.status = 'completed'
  GROUP BY t.route_id
)
SELECT r.route_code, r.origin_city, r.destination_city,
       entregas,
       ROUND(peaje_total::numeric / NULLIF(entregas,0), 2) AS peaje_por_entrega
FROM rtd
JOIN routes r ON r.route_id = rtd.route_id
ORDER BY peaje_por_entrega DESC
LIMIT 10;

