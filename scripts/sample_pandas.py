#!/usr/bin/env python3
"""
Sample script using the 'pandas' library.
Creates and analyzes sample data about server metrics.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def main():
    print("=" * 60)
    print("Server Metrics Analysis (using pandas library)")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Pandas version: {pd.__version__}")
    print(f"NumPy version: {np.__version__}")
    print()

    # Generate sample server metrics data
    np.random.seed(42)  # For reproducibility

    servers = ['web-01', 'web-02', 'db-01', 'cache-01', 'api-01']
    num_records = 20

    # Create sample data
    data = {
        'timestamp': [datetime.now() - timedelta(hours=i) for i in range(num_records)],
        'server': np.random.choice(servers, num_records),
        'cpu_percent': np.random.uniform(10, 95, num_records).round(1),
        'memory_percent': np.random.uniform(20, 85, num_records).round(1),
        'disk_io_mb': np.random.uniform(5, 500, num_records).round(2),
        'network_mb': np.random.uniform(1, 100, num_records).round(2),
        'requests_per_sec': np.random.randint(100, 5000, num_records)
    }

    df = pd.DataFrame(data)

    print("Sample Data (last 5 records):")
    print("-" * 60)
    print(df.tail().to_string(index=False))
    print()

    # Analysis by server
    print("Statistics by Server:")
    print("-" * 60)
    server_stats = df.groupby('server').agg({
        'cpu_percent': ['mean', 'max'],
        'memory_percent': ['mean', 'max'],
        'requests_per_sec': ['sum', 'mean']
    }).round(2)

    # Flatten column names
    server_stats.columns = ['_'.join(col).strip() for col in server_stats.columns.values]
    print(server_stats.to_string())
    print()

    # Overall statistics
    print("Overall Statistics:")
    print("-" * 60)
    overall = {
        'total_records': len(df),
        'unique_servers': df['server'].nunique(),
        'avg_cpu': round(df['cpu_percent'].mean(), 2),
        'max_cpu': round(df['cpu_percent'].max(), 2),
        'avg_memory': round(df['memory_percent'].mean(), 2),
        'total_requests': int(df['requests_per_sec'].sum()),
        'avg_requests_per_sec': round(df['requests_per_sec'].mean(), 2)
    }

    for key, value in overall.items():
        print(f"  {key}: {value}")
    print()

    # High CPU alerts
    high_cpu = df[df['cpu_percent'] > 80]
    if len(high_cpu) > 0:
        print(f"High CPU Alerts (>80%): {len(high_cpu)} instances")
        print("-" * 60)
        print(high_cpu[['timestamp', 'server', 'cpu_percent']].to_string(index=False))
    else:
        print("No high CPU alerts detected.")

    print()
    print("Analysis complete!")

    return 0

if __name__ == "__main__":
    exit(main())
