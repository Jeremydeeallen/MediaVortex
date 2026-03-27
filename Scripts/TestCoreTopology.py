"""
Test script for CoreTopologyService and new CpuAffinityService.
Run: py Scripts/TestCoreTopology.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil

print("=" * 60)
print("CPU TOPOLOGY DETECTION TEST")
print("=" * 60)

# Basic psutil info
print(f"\npsutil.cpu_count(logical=True):  {psutil.cpu_count(logical=True)}")
print(f"psutil.cpu_count(logical=False): {psutil.cpu_count(logical=False)}")

# Test CoreTopologyService
print("\n" + "-" * 60)
print("CoreTopologyService Detection")
print("-" * 60)

from Services.CoreTopologyService import CoreTopologyService

Topology = CoreTopologyService()
Summary = Topology.GetTopologySummary()

print(f"Detection Method:  {Summary['DetectionMethod']}")
print(f"Is Hybrid:         {Summary['IsHybrid']}")
print(f"P-Core Count:      {Summary['PCoreCount']}")
print(f"E-Core Count:      {Summary['ECoreCount']}")
print(f"Total Logical:     {Summary['TotalLogical']}")
print(f"P-Core Logical IDs: {Summary['PCoreLogicalIds']}")
print(f"E-Core Logical IDs: {Summary['ECoreLogicalIds']}")
print(f"P-Core Physical IDs (no HT): {Summary['PCorePhysicalIds']}")

# Test tier selection
print("\n" + "-" * 60)
print("Tier Selection")
print("-" * 60)

for Tier in ["performance", "performance-all", "efficiency", "all"]:
    Cores = Topology.GetCoresForTier(Tier, MaxCount=8)
    print(f"  Tier '{Tier}' (max 8): {Cores}")

# Quick sanity checks
print("\n" + "-" * 60)
print("Sanity Checks")
print("-" * 60)

TotalLogical = psutil.cpu_count(logical=True)
Errors = []

if Summary['TotalLogical'] != TotalLogical:
    Errors.append(f"Total logical mismatch: {Summary['TotalLogical']} vs psutil {TotalLogical}")

if Summary['PCoreCount'] + Summary['ECoreCount'] != Summary['TotalLogical']:
    Errors.append(f"P+E cores ({Summary['PCoreCount']}+{Summary['ECoreCount']}) != Total ({Summary['TotalLogical']})")

if Summary['IsHybrid']:
    PCorePhysical = Topology.GetPCorePhysicalIds()
    if len(PCorePhysical) == 0:
        Errors.append("Hybrid detected but no P-core physical IDs")

    ECores = Topology.GetECoreIds()
    if len(ECores) == 0:
        Errors.append("Hybrid detected but no E-core IDs")

    # Check no overlap
    Overlap = set(Summary['PCoreLogicalIds']) & set(Summary['ECoreLogicalIds'])
    if Overlap:
        Errors.append(f"P-core and E-core IDs overlap: {Overlap}")

if Errors:
    print("FAILURES:")
    for Err in Errors:
        print(f"  ✗ {Err}")
else:
    print("  ✓ All checks passed")

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
