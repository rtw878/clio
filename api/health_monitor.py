"""
API Health Monitoring System for TNA Discovery API

Implements comprehensive health monitoring from TNA Bible Recommendations
"""

import logging
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import statistics
import json
from pathlib import Path
import sqlite3
from collections import deque, defaultdict

from .client import DiscoveryClient, TransientError, PermanentError, RateLimitError, AuthenticationError

logger = logging.getLogger(__name__)


@dataclass
class HealthCheck:
    """Individual health check result"""
    endpoint: str
    timestamp: float
    success: bool
    response_time: float
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None


@dataclass
class EndpointHealth:
    """Health statistics for a specific endpoint"""
    endpoint: str
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    average_response_time: float = 0.0
    last_success: Optional[float] = None
    last_failure: Optional[float] = None
    consecutive_failures: int = 0
    error_rate_5min: float = 0.0
    error_rate_1hour: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.total_checks == 0:
            return 0.0
        return (self.successful_checks / self.total_checks) * 100
    
    @property
    def availability_status(self) -> str:
        """Get availability status string"""
        if self.consecutive_failures >= 5:
            return "DOWN"
        elif self.consecutive_failures >= 2:
            return "DEGRADED"
        elif self.success_rate >= 95:
            return "HEALTHY"
        elif self.success_rate >= 90:
            return "WARNING"
        else:
            return "CRITICAL"


class APIHealthMonitor:
    """
    Comprehensive API health monitoring system
    
    Features:
    - Real-time endpoint health checking
    - Response time tracking
    - Error rate monitoring
    - Automatic alert generation
    - Health dashboard data
    - Historical trending
    """
    
    def __init__(self, 
                 api_client: DiscoveryClient,
                 check_interval: int = 60,
                 data_retention_hours: int = 168):  # 1 week
        """
        Initialize health monitor
        
        Args:
            api_client: DiscoveryClient instance
            check_interval: Seconds between health checks
            data_retention_hours: Hours to retain health data
        """
        self.api_client = api_client
        self.check_interval = check_interval
        self.data_retention_hours = data_retention_hours
        
        # Health data storage
        self.health_checks: deque = deque(maxlen=10000)  # Recent checks
        self.endpoint_health: Dict[str, EndpointHealth] = {}
        
        # Monitoring state
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Alert configuration
        self.alert_callbacks: List[Callable] = []
        self.alert_thresholds = {
            'consecutive_failures': 3,
            'error_rate_5min': 50.0,  # 50% error rate
            'response_time_threshold': 5.0  # 5 seconds
        }
        
        # Endpoints to monitor
        self.monitored_endpoints = [
            ('search/v1/records', {'sps.searchQuery': 'test', 'sps.resultsPageSize': 1}),
            ('records/v1/details/C9134', {}),  # Known record
            ('fileauthorities/v1/collection/Person', {'limit': 1}),
            ('repository/v1/collection', {'limit': 1})
        ]
        
        # Initialize health database
        self._init_health_db()
        
        logger.info(f"Initialized APIHealthMonitor (interval={check_interval}s)")
    
    def _init_health_db(self):
        """Initialize SQLite database for health data persistence"""
        health_db_path = Path("data/health.db")
        health_db_path.parent.mkdir(exist_ok=True)
        
        with sqlite3.connect(health_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    success BOOLEAN NOT NULL,
                    response_time REAL NOT NULL,
                    status_code INTEGER,
                    error_message TEXT,
                    error_type TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_health_endpoint_time 
                ON health_checks(endpoint, timestamp)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_health_timestamp 
                ON health_checks(timestamp)
            """)
            
            conn.commit()
    
    def add_alert_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """
        Add a callback function for health alerts
        
        Args:
            callback: Function to call with (alert_type, alert_data)
        """
        self.alert_callbacks.append(callback)
        logger.info("Added health alert callback")
    
    def start_monitoring(self):
        """Start the health monitoring thread"""
        if not self.is_monitoring:
            self.is_monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("Started API health monitoring")
    
    def stop_monitoring(self):
        """Stop the health monitoring thread"""
        self.is_monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)
        logger.info("Stopped API health monitoring")
    
    def perform_health_check(self, endpoint: str, params: Dict[str, Any]) -> HealthCheck:
        """
        Perform a single health check on an endpoint
        
        Args:
            endpoint: API endpoint to check
            params: Parameters for the request
            
        Returns:
            HealthCheck result
        """
        start_time = time.time()
        
        try:
            # Make the API request
            response_data = self.api_client._make_request(endpoint, params)
            
            response_time = time.time() - start_time
            
            # Successful request
            health_check = HealthCheck(
                endpoint=endpoint,
                timestamp=start_time,
                success=True,
                response_time=response_time,
                status_code=200
            )
            
            logger.debug(f"Health check successful for {endpoint} ({response_time:.3f}s)")
            
        except AuthenticationError as e:
            response_time = time.time() - start_time
            health_check = HealthCheck(
                endpoint=endpoint,
                timestamp=start_time,
                success=False,
                response_time=response_time,
                status_code=401,
                error_message=str(e),
                error_type="AuthenticationError"
            )
            
        except RateLimitError as e:
            response_time = time.time() - start_time
            health_check = HealthCheck(
                endpoint=endpoint,
                timestamp=start_time,
                success=False,
                response_time=response_time,
                status_code=429,
                error_message=str(e),
                error_type="RateLimitError"
            )
            
        except TransientError as e:
            response_time = time.time() - start_time
            health_check = HealthCheck(
                endpoint=endpoint,
                timestamp=start_time,
                success=False,
                response_time=response_time,
                status_code=500,
                error_message=str(e),
                error_type="TransientError"
            )
            
        except PermanentError as e:
            response_time = time.time() - start_time
            health_check = HealthCheck(
                endpoint=endpoint,
                timestamp=start_time,
                success=False,
                response_time=response_time,
                status_code=404,
                error_message=str(e),
                error_type="PermanentError"
            )
            
        except Exception as e:
            response_time = time.time() - start_time
            health_check = HealthCheck(
                endpoint=endpoint,
                timestamp=start_time,
                success=False,
                response_time=response_time,
                error_message=str(e),
                error_type="UnknownError"
            )
        
        # Store the health check
        self._record_health_check(health_check)
        
        return health_check
    
    def _record_health_check(self, health_check: HealthCheck):
        """Record a health check result"""
        # Add to memory store
        self.health_checks.append(health_check)
        
        # Update endpoint health statistics
        self._update_endpoint_health(health_check)
        
        # Store in database
        self._store_health_check_db(health_check)
        
        # Check for alerts
        self._check_alerts(health_check)
    
    def _update_endpoint_health(self, health_check: HealthCheck):
        """Update endpoint health statistics"""
        endpoint = health_check.endpoint
        
        if endpoint not in self.endpoint_health:
            self.endpoint_health[endpoint] = EndpointHealth(endpoint=endpoint)
        
        health = self.endpoint_health[endpoint]
        
        # Update basic counters
        health.total_checks += 1
        
        if health_check.success:
            health.successful_checks += 1
            health.last_success = health_check.timestamp
            health.consecutive_failures = 0
        else:
            health.failed_checks += 1
            health.last_failure = health_check.timestamp
            health.consecutive_failures += 1
        
        # Update average response time
        if health.total_checks == 1:
            health.average_response_time = health_check.response_time
        else:
            # Rolling average
            health.average_response_time = (
                (health.average_response_time * (health.total_checks - 1) + health_check.response_time) 
                / health.total_checks
            )
        
        # Calculate error rates
        current_time = health_check.timestamp
        
        # 5-minute error rate
        recent_checks_5min = [
            check for check in self.health_checks
            if check.endpoint == endpoint and (current_time - check.timestamp) <= 300
        ]
        if recent_checks_5min:
            health.error_rate_5min = (
                sum(1 for check in recent_checks_5min if not check.success) / 
                len(recent_checks_5min) * 100
            )
        
        # 1-hour error rate
        recent_checks_1hour = [
            check for check in self.health_checks
            if check.endpoint == endpoint and (current_time - check.timestamp) <= 3600
        ]
        if recent_checks_1hour:
            health.error_rate_1hour = (
                sum(1 for check in recent_checks_1hour if not check.success) / 
                len(recent_checks_1hour) * 100
            )
    
    def _store_health_check_db(self, health_check: HealthCheck):
        """Store health check in database"""
        try:
            health_db_path = Path("data/health.db")
            
            with sqlite3.connect(health_db_path) as conn:
                conn.execute("""
                    INSERT INTO health_checks 
                    (endpoint, timestamp, success, response_time, status_code, error_message, error_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    health_check.endpoint,
                    health_check.timestamp,
                    health_check.success,
                    health_check.response_time,
                    health_check.status_code,
                    health_check.error_message,
                    health_check.error_type
                ))
                conn.commit()
                
        except Exception as e:
            logger.warning(f"Failed to store health check in database: {e}")
    
    def _check_alerts(self, health_check: HealthCheck):
        """Check if health check triggers any alerts"""
        endpoint = health_check.endpoint
        health = self.endpoint_health.get(endpoint)
        
        if not health:
            return
        
        alerts = []
        
        # Consecutive failures alert
        if health.consecutive_failures >= self.alert_thresholds['consecutive_failures']:
            alerts.append({
                'type': 'consecutive_failures',
                'endpoint': endpoint,
                'consecutive_failures': health.consecutive_failures,
                'last_error': health_check.error_message
            })
        
        # High error rate alert
        if health.error_rate_5min >= self.alert_thresholds['error_rate_5min']:
            alerts.append({
                'type': 'high_error_rate',
                'endpoint': endpoint,
                'error_rate_5min': health.error_rate_5min,
                'error_rate_1hour': health.error_rate_1hour
            })
        
        # Slow response time alert
        if health_check.response_time >= self.alert_thresholds['response_time_threshold']:
            alerts.append({
                'type': 'slow_response',
                'endpoint': endpoint,
                'response_time': health_check.response_time,
                'average_response_time': health.average_response_time
            })
        
        # Send alerts
        for alert in alerts:
            self._send_alert(alert['type'], alert)
    
    def _send_alert(self, alert_type: str, alert_data: Dict[str, Any]):
        """Send an alert to all registered callbacks"""
        for callback in self.alert_callbacks:
            try:
                callback(alert_type, alert_data)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
        
        # Log the alert
        logger.warning(f"HEALTH ALERT ({alert_type}): {alert_data}")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Started health monitoring loop")
        
        while self.is_monitoring:
            try:
                # Perform health checks on all monitored endpoints
                for endpoint, params in self.monitored_endpoints:
                    if not self.is_monitoring:
                        break
                    
                    self.perform_health_check(endpoint, params)
                    
                    # Small delay between endpoint checks
                    time.sleep(1)
                
                # Clean up old data
                self._cleanup_old_data()
                
                # Wait for next check interval
                if self.is_monitoring:
                    time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
                time.sleep(10)  # Brief pause before retrying
        
        logger.info("Health monitoring loop ended")
    
    def _cleanup_old_data(self):
        """Clean up old health data"""
        try:
            cutoff_time = time.time() - (self.data_retention_hours * 3600)
            
            # Clean up memory store
            self.health_checks = deque(
                [check for check in self.health_checks if check.timestamp > cutoff_time],
                maxlen=self.health_checks.maxlen
            )
            
            # Clean up database
            health_db_path = Path("data/health.db")
            with sqlite3.connect(health_db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM health_checks WHERE timestamp < ?",
                    (cutoff_time,)
                )
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    logger.debug(f"Cleaned up {deleted_count} old health check records")
                conn.commit()
                
        except Exception as e:
            logger.warning(f"Error cleaning up health data: {e}")
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary"""
        current_time = time.time()
        
        # Overall statistics
        total_endpoints = len(self.endpoint_health)
        healthy_endpoints = sum(
            1 for health in self.endpoint_health.values() 
            if health.availability_status == "HEALTHY"
        )
        
        # Recent checks (last hour)
        recent_checks = [
            check for check in self.health_checks
            if (current_time - check.timestamp) <= 3600
        ]
        
        if recent_checks:
            overall_success_rate = (
                sum(1 for check in recent_checks if check.success) / 
                len(recent_checks) * 100
            )
            average_response_time = statistics.mean(check.response_time for check in recent_checks)
        else:
            overall_success_rate = 0.0
            average_response_time = 0.0
        
        # Determine overall status
        if healthy_endpoints == total_endpoints and overall_success_rate >= 95:
            overall_status = "HEALTHY"
        elif overall_success_rate >= 90:
            overall_status = "WARNING"
        elif overall_success_rate >= 75:
            overall_status = "DEGRADED"
        else:
            overall_status = "CRITICAL"
        
        return {
            'overall_status': overall_status,
            'total_endpoints': total_endpoints,
            'healthy_endpoints': healthy_endpoints,
            'overall_success_rate': round(overall_success_rate, 2),
            'average_response_time': round(average_response_time, 3),
            'total_checks_last_hour': len(recent_checks),
            'monitoring_active': self.is_monitoring,
            'check_interval': self.check_interval,
            'endpoints': {
                endpoint: {
                    'status': health.availability_status,
                    'success_rate': round(health.success_rate, 2),
                    'average_response_time': round(health.average_response_time, 3),
                    'consecutive_failures': health.consecutive_failures,
                    'error_rate_5min': round(health.error_rate_5min, 2),
                    'last_check': health.last_success or health.last_failure
                }
                for endpoint, health in self.endpoint_health.items()
            }
        }
    
    def get_endpoint_history(self, 
                           endpoint: str, 
                           hours: int = 24) -> List[Dict[str, Any]]:
        """Get historical data for a specific endpoint"""
        cutoff_time = time.time() - (hours * 3600)
        
        endpoint_checks = [
            {
                'timestamp': check.timestamp,
                'success': check.success,
                'response_time': check.response_time,
                'error_type': check.error_type,
                'error_message': check.error_message
            }
            for check in self.health_checks
            if check.endpoint == endpoint and check.timestamp > cutoff_time
        ]
        
        return sorted(endpoint_checks, key=lambda x: x['timestamp'])
    
    def get_error_analysis(self, hours: int = 24) -> Dict[str, Any]:
        """Get error analysis for the specified time period"""
        cutoff_time = time.time() - (hours * 3600)
        
        recent_checks = [
            check for check in self.health_checks
            if check.timestamp > cutoff_time
        ]
        
        failed_checks = [check for check in recent_checks if not check.success]
        
        if not failed_checks:
            return {
                'total_errors': 0,
                'error_rate': 0.0,
                'error_types': {},
                'error_endpoints': {}
            }
        
        # Count errors by type
        error_types = defaultdict(int)
        for check in failed_checks:
            error_types[check.error_type or 'Unknown'] += 1
        
        # Count errors by endpoint
        error_endpoints = defaultdict(int)
        for check in failed_checks:
            error_endpoints[check.endpoint] += 1
        
        return {
            'total_errors': len(failed_checks),
            'error_rate': round((len(failed_checks) / len(recent_checks)) * 100, 2),
            'error_types': dict(error_types),
            'error_endpoints': dict(error_endpoints),
            'most_common_error': max(error_types.items(), key=lambda x: x[1])[0] if error_types else None
        }
    
    def __enter__(self):
        """Context manager entry"""
        self.start_monitoring()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_monitoring()


# Global health monitor instance
_health_monitor: Optional[APIHealthMonitor] = None


def get_health_monitor(api_client: Optional[DiscoveryClient] = None) -> APIHealthMonitor:
    """Get or create global health monitor instance"""
    global _health_monitor
    if _health_monitor is None and api_client:
        _health_monitor = APIHealthMonitor(api_client)
    return _health_monitor


def setup_console_alerts():
    """Setup basic console-based alert system"""
    def console_alert_handler(alert_type: str, alert_data: Dict[str, Any]):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n🚨 HEALTH ALERT [{timestamp}] - {alert_type.upper()}")
        
        if alert_type == 'consecutive_failures':
            print(f"   Endpoint: {alert_data['endpoint']}")
            print(f"   Consecutive Failures: {alert_data['consecutive_failures']}")
            print(f"   Last Error: {alert_data['last_error']}")
        elif alert_type == 'high_error_rate':
            print(f"   Endpoint: {alert_data['endpoint']}")
            print(f"   5-min Error Rate: {alert_data['error_rate_5min']:.1f}%")
            print(f"   1-hour Error Rate: {alert_data['error_rate_1hour']:.1f}%")
        elif alert_type == 'slow_response':
            print(f"   Endpoint: {alert_data['endpoint']}")
            print(f"   Response Time: {alert_data['response_time']:.3f}s")
            print(f"   Average: {alert_data['average_response_time']:.3f}s")
        
        print()
    
    return console_alert_handler
