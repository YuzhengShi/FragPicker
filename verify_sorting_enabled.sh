#!/bin/bash
# Verification script for enable_sorting=True throughout codebase

echo "=================================================="
echo "  Sorting Status Verification"
echo "=================================================="
echo ""

echo "1️⃣  Checking TEST files (should have NO enable_sorting=False):"
echo "-----------------------------------------------------------"
TEST_FALSE=$(grep -r "enable_sorting=False" tests/ 2>/dev/null | wc -l)
if [ "$TEST_FALSE" -eq 0 ]; then
    echo "✅ PASS: No enable_sorting=False found in tests/"
else
    echo "❌ FAIL: Found $TEST_FALSE occurrences of enable_sorting=False in tests/"
    grep -r "enable_sorting=False" tests/
fi
echo ""

echo "2️⃣  Checking BENCHMARK files (should KEEP enable_sorting=False):"
echo "----------------------------------------------------------------"
BENCH_FALSE=$(grep -r "enable_sorting=False" benchmarks/ 2>/dev/null | wc -l)
if [ "$BENCH_FALSE" -ge 5 ]; then
    echo "✅ PASS: Found $BENCH_FALSE occurrences in benchmarks/ (correct)"
else
    echo "⚠️  WARNING: Only found $BENCH_FALSE occurrences in benchmarks/"
fi
echo ""

echo "3️⃣  Checking PRODUCTION code (processing.py):"
echo "----------------------------------------------"
PROD_TRUE=$(grep "enable_sorting=True" src/analysis/processing.py 2>/dev/null | wc -l)
if [ "$PROD_TRUE" -ge 1 ]; then
    echo "✅ PASS: processing.py uses enable_sorting=True"
else
    echo "❌ FAIL: processing.py does not use enable_sorting=True"
fi
echo ""

echo "4️⃣  Checking PROCESSOR defaults:"
echo "-----------------------------------"
PARALLEL_DEFAULT=$(grep -A2 "def process_files" src/analysis/parallel_analyzer/parallel_processor.py | grep "enable_sorting: bool = True")
MULTIPROC_DEFAULT=$(grep -A2 "def process_files" src/analysis/parallel_analyzer/multiprocess_processor.py | grep "enable_sorting: bool = True")

if [ -n "$PARALLEL_DEFAULT" ]; then
    echo "✅ PASS: parallel_processor.py defaults to True"
else
    echo "❌ FAIL: parallel_processor.py does not default to True"
fi

if [ -n "$MULTIPROC_DEFAULT" ]; then
    echo "✅ PASS: multiprocess_processor.py defaults to True"
else
    echo "❌ FAIL: multiprocess_processor.py does not default to True"
fi
echo ""

echo "5️⃣  Running quick test verification:"
echo "-------------------------------------"
if [ -f ".venv/bin/python" ]; then
    echo "Running test_sorting_verification.py..."
    .venv/bin/python tests/test_sorting_verification.py 2>&1 | tail -5
else
    echo "⚠️  Virtual environment not found, skipping test run"
fi
echo ""

echo "=================================================="
echo "  Verification Complete"
echo "=================================================="
echo ""

# Summary
if [ "$TEST_FALSE" -eq 0 ] && [ "$BENCH_FALSE" -ge 5 ] && [ "$PROD_TRUE" -ge 1 ] && [ -n "$PARALLEL_DEFAULT" ] && [ -n "$MULTIPROC_DEFAULT" ]; then
    echo "🎉 ✅ ALL CHECKS PASSED!"
    echo ""
    echo "Summary:"
    echo "  ✅ Tests have sorting enabled"
    echo "  ✅ Benchmarks keep sorting disabled"
    echo "  ✅ Production code uses sorting"
    echo "  ✅ Both processors default to sorting=True"
    echo ""
    exit 0
else
    echo "⚠️  Some checks failed. Review the output above."
    exit 1
fi
