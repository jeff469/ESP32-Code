"""
Legacy entrypoint preserved for compatibility. The original monolithic script
has been split into smaller modules under ``tests/hydronic_slab`` so that
individual pieces can be tested independently.
"""
from tests.hydronic_slab.main import main

if __name__ == "__main__":
    main()
