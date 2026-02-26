rm /home/thangdd/repos/TerrARA/.cursor/debug.log#!/bin/bash
# Script to install rapidfuzz for faster fuzzy matching

echo "Installing rapidfuzz for 10-100x faster fuzzy matching..."
pip install rapidfuzz

if [ $? -eq 0 ]; then
    echo "✓ rapidfuzz installed successfully"
    echo ""
    echo "Testing import..."
    python3 -c "
from implicit_dependency_resolver.fuzzy_matching import FuzzyMatcher, USE_RAPIDFUZZ
if USE_RAPIDFUZZ:
    print('✓ rapidfuzz is now active (fast mode)')
    print('Performance improvement: 10-100x faster than difflib')
else:
    print('✗ rapidfuzz still not available')
    exit(1)
"
else
    echo "✗ Failed to install rapidfuzz"
    exit(1)
fi
