-- =====================================================
-- FLEETLOGIX - ÍNDICES DE OPTIMIZACIÓN
-- Avance 2 - Mejora de Performance
-- =====================================================

-- ÍNDICE 1: Para queries con filtros por fecha en trips
-- Beneficia: Query 4, Query 6, Query 11
CREATE INDEX IF NOT EXISTS idx_trips_departure_status 
ON trips(departure_datetime, status);

-- ÍNDICE 2: Para JOINs entre deliveries y trips
-- Beneficia: Query 4, Query 6 (mejora JOIN deliveries→trips)
CREATE INDEX IF NOT EXISTS idx_deliveries_trip_id 
ON deliveries(trip_id);

-- ÍNDICE 3: Para filtros de estado en drivers
-- Beneficia: Query 5 (WHERE status = 'active')
CREATE INDEX IF NOT EXISTS idx_drivers_status 
ON drivers(status);

-- ÍNDICE 4: Para JOINs entre trips y drivers  
-- Beneficia: Query 5, Query 6 (mejora JOIN trips→drivers)
CREATE INDEX IF NOT EXISTS idx_trips_driver_id 
ON trips(driver_id);

-- ÍNDICE 5: Para agregaciones y filtros por tipo de vehículo
-- Beneficia: Query 1, Query 9 (GROUP BY vehicle_type)
CREATE INDEX IF NOT EXISTS idx_vehicles_type 
ON vehicles(vehicle_type);

-- ÍNDICES ADICIONALES:
-- Para query de entregas tardías por conductor (últimos 90 días)
CREATE INDEX idx_deliveries_sched_deliv 
ON deliveries (scheduled_datetime, delivered_datetime);

-- Para query de utilización de capacidad por vehículo (últimos 60 días)
CREATE INDEX idx_trips_vehicle_status_departure 
ON trips (vehicle_id, status, departure_datetime);

-- Para query de top 10 rutas por costo de peaje efectivo por entrega (últimos 30 días)
CREATE INDEX idx_trips_route_status_departure 
ON trips (route_id, status, departure_datetime);

-- Verificar índices creados
SELECT 
    tablename, 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE schemaname = 'public' 
ORDER BY tablename;