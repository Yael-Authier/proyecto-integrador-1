"""
FleetLogix: Funciones Lambda para AWS (Avance 4)
-------------------------------------------------
Este módulo define tres funciones Lambda diseñadas para operar
en una arquitectura serverless basada en AWS:
- Verificar si una entrega se completó (DynamoDB)
- Calcular el tiempo estimado de llegada (ETA)
- Enviar alertas si se detectan desvíos de ruta
Las funciones no se ejecutan localmente; su código es teórico
y forma parte de la documentación del diseño cloud.
"""

import json
import boto3
from datetime import datetime, timedelta
from decimal import Decimal

# ---------------------------
# 0) Clientes AWS (teórico)
# ---------------------------
# En despliegue real, se inyectan permisos via IAM Role.
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

# =====================================================
# 1) LAMBDA: Verificar si una entrega se completó
# =====================================================
# Idea: recibir delivery_id y consultar estado en DynamoDB (deliveries_status).
def lambda_verificar_entrega(event, context):
    """
    Verifica si una entrega se completó consultando la tabla deliveries_status.
    Entradas (JSON):
      - delivery_id (str, requerido)
      - tracking_number (str, opcional)
    Respuesta:
      - 200 con {delivery_id, tracking_number, is_completed, status, delivered_datetime}
      - 404 si no existe
      - 400 si faltan parámetros
    """
    delivery_id = event.get('delivery_id')
    if not delivery_id:
        return {'statusCode': 400, 'body': json.dumps({'error': 'delivery_id es requerido'})}

    table = dynamodb.Table('deliveries_status')
    try:
        response = table.get_item(Key={'delivery_id': delivery_id})
        if 'Item' not in response:
            return {'statusCode': 404, 'body': json.dumps({'error': 'Entrega no encontrada', 'delivery_id': delivery_id})}

        item = response['Item']
        is_completed = item.get('status') == 'delivered'
        return {
            'statusCode': 200,
            'body': json.dumps({
                'delivery_id': delivery_id,
                'tracking_number': item.get('tracking_number'),
                'is_completed': is_completed,
                'status': item.get('status'),
                'delivered_datetime': str(item.get('delivered_datetime', ''))
            })
        }
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

# =====================================================
# 2) LAMBDA: Calcular tiempo estimado de llegada (ETA)
# =====================================================
# Idea: calcular distancia aprox entre posición actual y destino, estimar ETA y guardar snapshot en vehicle_tracking.
def lambda_calcular_eta(event, context):
    """
    Calcula ETA con distancia aproximada (Haversine simplificado).
    Entradas (JSON):
      - vehicle_id (str)
      - current_location {lat, lon}
      - destination {lat, lon}
      - current_speed_kmh (num, default 60)
    Respuesta: 200 con distance_remaining_km, eta y estimated_minutes
    """
    vehicle_id = event.get('vehicle_id')
    current_location = event.get('current_location')  # {lat, lon}
    destination = event.get('destination')            # {lat, lon}
    current_speed_kmh = event.get('current_speed_kmh', 60)

    if not all([vehicle_id, current_location, destination]):
        return {'statusCode': 400, 'body': json.dumps({'error': 'Faltan parámetros requeridos'})}

    try:
        # Distancia en km (aprox: 111 km por grado)
        lat_diff = abs(destination['lat'] - current_location['lat'])
        lon_diff = abs(destination['lon'] - current_location['lon'])
        distance_km = ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111

        # Tiempo y ETA
        if current_speed_kmh > 0:
            hours = distance_km / float(current_speed_kmh)
            eta = datetime.now() + timedelta(hours=hours)
        else:
            eta, hours = None, 0

        # Persistencia operativa (teórica) en DynamoDB
        table = dynamodb.Table('vehicle_tracking')
        table.put_item(Item={
            'vehicle_id': vehicle_id,
            'timestamp': datetime.now().isoformat(),
            'current_location': current_location,
            'destination': destination,
            'distance_remaining_km': Decimal(str(round(distance_km, 2))),
            'eta': eta.isoformat() if eta else None,
            'current_speed_kmh': Decimal(str(current_speed_kmh))
        })

        return {
            'statusCode': 200,
            'body': json.dumps({
                'vehicle_id': vehicle_id,
                'distance_remaining_km': round(distance_km, 2),
                'eta': eta.isoformat() if eta else 'No disponible',
                'estimated_minutes': round(hours * 60) if eta else None
            })
        }
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

# =====================================================
# 3) LAMBDA: Enviar alerta si camión se desvía de ruta
# =====================================================
# Idea: comparar posición actual vs waypoints de la ruta (routes_waypoints) y alertar por SNS si se excede umbral.
def lambda_alerta_desvio(event, context):
    """
    Detecta desvíos de ruta y publica alerta en SNS si corresponde.
    Entradas (JSON):
      - vehicle_id (str), driver_id (num), route_id (str), current_location {lat, lon}
    Respuesta: 200 con is_deviated, deviation_km, threshold_km y alert_sent
    """
    vehicle_id = event.get('vehicle_id')
    current_location = event.get('current_location')  # {lat, lon}
    route_id = event.get('route_id')
    driver_id = event.get('driver_id')

    if not all([vehicle_id, current_location, route_id]):
        return {'statusCode': 400, 'body': json.dumps({'error': 'Faltan parámetros requeridos'})}

    try:
        # Obtener waypoints de la ruta
        table = dynamodb.Table('routes_waypoints')
        response = table.get_item(Key={'route_id': route_id})
        if 'Item' not in response:
            return {'statusCode': 404, 'body': json.dumps({'error': 'Ruta no encontrada'})}

        waypoints = response['Item'].get('waypoints', [])

        # Distancia mínima (aprox 111 km por grado)
        min_distance = float('inf')
        for wp in waypoints:
            lat_diff = abs(wp['lat'] - current_location['lat'])
            lon_diff = abs(wp['lon'] - current_location['lon'])
            distance = ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111
            min_distance = min(min_distance, distance)

        DEVIATION_THRESHOLD_KM = 5
        is_deviated = min_distance > DEVIATION_THRESHOLD_KM

        alert_sent = False
        if is_deviated:
            message = {
                'vehicle_id': vehicle_id,
                'driver_id': driver_id,
                'route_id': route_id,
                'deviation_km': round(min_distance, 2),
                'current_location': current_location,
                'timestamp': datetime.now().isoformat(),
                'alert_type': 'ROUTE_DEVIATION'
            }
            # Publicación SNS (teórico)
            sns.publish(
                TopicArn='arn:aws:sns:us-east-1:123456789012:fleetlogix-alerts',
                Message=json.dumps(message),
                Subject='Alerta: Desvío de Ruta Detectado'
            )
            # Guardado de auditoría (teórico)
            alerts_table = dynamodb.Table('alerts_history')
            alerts_table.put_item(Item=message)
            alert_sent = True

        return {
            'statusCode': 200,
            'body': json.dumps({
                'vehicle_id': vehicle_id,
                'is_deviated': is_deviated,
                'deviation_km': round(min_distance, 2),
                'alert_sent': alert_sent,
                'threshold_km': DEVIATION_THRESHOLD_KM
            })
        }
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

# =====================================================
# 4) Configuración de orígenes/automatización (teórico)
# =====================================================
"""
Sugerencias de triggers (teóricas):
- Lambda 1 (verificar_entrega): API Gateway POST /deliveries/verify
- Lambda 2 (calcular_eta): EventBridge (cron) cada 5 minutos
- Lambda 3 (alerta_desvio): API Gateway POST /telemetry/route-check o Kinesis con GPS
"""
