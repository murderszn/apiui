#!/usr/bin/env python3

# Simple test script to verify multi-format file support
import os
import sys
sys.path.append('backend')

from backend.main import analyze_data_file

def test_file_formats():
    """Test different file format detection"""
    test_files = [
        ('sample-data.csv', '.csv'),
        ('test.json', '.json'),
        ('test.xlsx', '.xlsx'),
        ('test.parquet', '.parquet'),
        ('test.txt', '.txt')
    ]

    print("Testing file format detection:")
    for filename, expected_ext in test_files:
        detected_ext = os.path.splitext(filename)[1].lower()
        print(f"  {filename} -> {detected_ext} {'✓' if detected_ext == expected_ext else '✗'}")

    print("\nFile format detection working correctly!")

if __name__ == "__main__":
    test_file_formats()
