import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from google.cloud import monitoring_v3
from google.api_core.exceptions import NotFound, PermissionDenied
from core.config import settings

class CloudMetricsService:
    def __init__(self):
        self.client = None
        self.project_name = f"projects/{settings.gcp_project_id}" if hasattr(settings, 'gcp_project_id') and settings.gcp_project_id else None

    def _get_client(self):
        """Lazy initialization of the monitoring client"""
        if self.client is None and self.project_name:
            try:
                self.client = monitoring_v3.MetricServiceClient()
            except Exception as e:
                print(f"Failed to initialize Cloud Monitoring client: {str(e)}")
                self.client = None
        return self.client

    async def get_cloud_run_metrics(self, service_name: str, hours: int = 24) -> Dict[str, Any]:
        """
        Fetch real Cloud Run metrics for a service

        Args:
            service_name: Cloud Run service name (e.g., 'apiui-abc12345')
            hours: Number of hours of data to fetch

        Returns:
            Dictionary containing metrics data
        """
        # Check if we can initialize the client
        if not self._get_client():
            print(f"Cloud Monitoring client not available, falling back to mock data for {service_name}")
            return self._get_fallback_metrics(hours)

        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)

            # Get various Cloud Run metrics
            request_count = await self._get_request_count(service_name, start_time, end_time)
            response_latencies = await self._get_response_latencies(service_name, start_time, end_time)
            error_count = await self._get_error_count(service_name, start_time, end_time)
            active_instances = await self._get_active_instances(service_name, start_time, end_time)

            # Process the data into hourly aggregations
            hourly_data = self._aggregate_hourly_data(
                request_count, response_latencies, error_count, active_instances, hours
            )

            # Calculate summary metrics
            summary = self._calculate_summary_metrics(hourly_data)

            return {
                'hourly_data': hourly_data,
                'summary': summary,
                'source': 'cloud_monitoring'
            }

        except Exception as e:
            print(f"Error fetching Cloud Run metrics for {service_name}: {str(e)}")
            # Return fallback data structure
            return self._get_fallback_metrics(hours)

    async def _get_request_count(self, service_name: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get request count metrics"""
        try:
            filter_str = f"""
            metric.type="run.googleapis.com/request_count"
            resource.type="cloud_run_revision"
            resource.label.service_name="{service_name}"
            """

            return await self._query_time_series(filter_str, start_time, end_time, "request_count")
        except Exception as e:
            print(f"Error fetching request count: {str(e)}")
            return []

    async def _get_response_latencies(self, service_name: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get response latency metrics"""
        try:
            filter_str = f"""
            metric.type="run.googleapis.com/request_latencies"
            resource.type="cloud_run_revision"
            resource.label.service_name="{service_name}"
            """

            return await self._query_time_series(filter_str, start_time, end_time, "response_latencies")
        except Exception as e:
            print(f"Error fetching response latencies: {str(e)}")
            return []

    async def _get_error_count(self, service_name: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get error count metrics"""
        try:
            filter_str = f"""
            metric.type="run.googleapis.com/request_count"
            metric.label.response_code_class="5xx"
            resource.type="cloud_run_revision"
            resource.label.service_name="{service_name}"
            """

            return await self._query_time_series(filter_str, start_time, end_time, "error_count")
        except Exception as e:
            print(f"Error fetching error count: {str(e)}")
            return []

    async def _get_active_instances(self, service_name: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get active instances count"""
        try:
            filter_str = f"""
            metric.type="run.googleapis.com/container/instance_count"
            resource.type="cloud_run_revision"
            resource.label.service_name="{service_name}"
            """

            return await self._query_time_series(filter_str, start_time, end_time, "active_instances")
        except Exception as e:
            print(f"Error fetching active instances: {str(e)}")
            return []

    async def _query_time_series(self, filter_str: str, start_time: datetime, end_time: datetime, metric_name: str) -> List[Dict]:
        """Query Cloud Monitoring time series data"""
        client = self._get_client()
        if not client:
            return []

        try:
            request = monitoring_v3.ListTimeSeriesRequest(
                name=self.project_name,
                filter=filter_str,
                interval=monitoring_v3.TimeInterval(
                    start_time=start_time,
                    end_time=end_time,
                ),
                aggregation=monitoring_v3.Aggregation(
                    alignment_period=timedelta(minutes=60),  # 1 hour alignment
                    per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_SUM if "count" in metric_name else monitoring_v3.Aggregation.Aligner.ALIGN_PERCENTILE_99,
                    cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_SUM if "count" in metric_name else monitoring_v3.Aggregation.Reducer.REDUCE_MEAN,
                ),
            )

            # Run in thread pool since google-cloud-monitoring is synchronous
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, client.list_time_series, request)

            data_points = []
            for time_series in response:
                for point in time_series.points:
                    timestamp = point.interval.start_time or point.interval.end_time
                    value = 0

                    if point.value.double_value is not None:
                        value = point.value.double_value
                    elif point.value.int64_value is not None:
                        value = point.value.int64_value
                    elif hasattr(point.value, 'distribution_value') and point.value.distribution_value:
                        # For latency distributions, get the 99th percentile
                        if hasattr(point.value.distribution_value, 'bucket_counts') and point.value.distribution_value.bucket_counts:
                            value = self._extract_percentile_from_distribution(point.value.distribution_value)

                    data_points.append({
                        'timestamp': timestamp,
                        'value': value,
                        'metric': metric_name
                    })

            return data_points

        except Exception as e:
            print(f"Error querying time series for {metric_name}: {str(e)}")
            return []

    def _extract_percentile_from_distribution(self, distribution_value) -> float:
        """Extract 99th percentile from distribution data"""
        try:
            # This is a simplified extraction - in practice you'd need to
            # properly calculate percentiles from bucket data
            if hasattr(distribution_value, 'mean'):
                return distribution_value.mean
            elif hasattr(distribution_value, 'sum_of_squared_deviation'):
                # Rough estimate for latency
                return 150  # Default reasonable latency in ms
        except:
            pass
        return 150  # Fallback latency

    def _aggregate_hourly_data(self, request_count: List[Dict], response_latencies: List[Dict],
                              error_count: List[Dict], active_instances: List[Dict], hours: int) -> List[Dict]:
        """Aggregate metrics data into hourly buckets"""
        hourly_data = []

        for hour_offset in range(hours):
            target_time = datetime.utcnow() - timedelta(hours=hour_offset)
            hour_start = target_time.replace(minute=0, second=0, microsecond=0)
            hour_end = hour_start + timedelta(hours=1)

            # Filter data for this hour
            hour_requests = [p for p in request_count if hour_start <= p['timestamp'].replace(tzinfo=None) < hour_end]
            hour_latencies = [p for p in response_latencies if hour_start <= p['timestamp'].replace(tzinfo=None) < hour_end]
            hour_errors = [p for p in error_count if hour_start <= p['timestamp'].replace(tzinfo=None) < hour_end]

            # Calculate aggregations
            total_requests = sum(p['value'] for p in hour_requests) if hour_requests else 0
            avg_latency = sum(p['value'] for p in hour_latencies) / len(hour_latencies) if hour_latencies else 0
            total_errors = sum(p['value'] for p in hour_errors) if hour_errors else 0

            hourly_data.append({
                'hour': hour_start.strftime('%H:00'),
                'requests': int(total_requests),
                'avg_response_time': round(avg_latency, 2),
                'errors': int(total_errors)
            })

        # Reverse to get chronological order (oldest first)
        return list(reversed(hourly_data))

    def _calculate_summary_metrics(self, hourly_data: List[Dict]) -> Dict[str, Any]:
        """Calculate summary metrics from hourly data"""
        if not hourly_data:
            return {
                'uptime_percentage': 100.0,
                'avg_response_time': 0,
                'total_requests': 0,
                'error_rate': 0,
                'last_updated': datetime.utcnow().isoformat()
            }

        total_requests = sum(h['requests'] for h in hourly_data)
        total_errors = sum(h['errors'] for h in hourly_data)

        # Calculate average response time
        response_times = [h['avg_response_time'] for h in hourly_data if h['avg_response_time'] > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        # Calculate error rate
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0

        # Calculate uptime based on hours with requests vs total hours
        hours_with_requests = sum(1 for h in hourly_data if h['requests'] > 0)
        uptime_percentage = min(99.9, (hours_with_requests / len(hourly_data)) * 100)

        return {
            'uptime_percentage': round(uptime_percentage, 1),
            'avg_response_time': round(avg_response_time, 2),
            'total_requests': total_requests,
            'error_rate': round(error_rate, 2),
            'last_updated': datetime.utcnow().isoformat()
        }

    def _get_fallback_metrics(self, hours: int) -> Dict[str, Any]:
        """Return fallback metrics when Cloud Monitoring fails"""
        hourly_data = []
        for i in range(hours):
            hour = (datetime.utcnow() - timedelta(hours=hours-i-1)).strftime('%H:00')
            hourly_data.append({
                'hour': hour,
                'requests': 0,
                'avg_response_time': 0,
                'errors': 0
            })

        return {
            'hourly_data': hourly_data,
            'summary': {
                'uptime_percentage': 100.0,
                'avg_response_time': 0,
                'total_requests': 0,
                'error_rate': 0,
                'last_updated': datetime.utcnow().isoformat()
            },
            'source': 'fallback'
        }
