"""NUCLEAR OPTION: Clear ALL Python and Numba cache files everywhere"""
import os
import shutil
import sys
import tempfile
import glob

def clear_numba_cache():
    """Delete EVERY possible cache location for Python and Numba"""
    deleted_count = 0
    
    print("\n1. Clearing workspace __pycache__ directories...")
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            cache_path = os.path.join(root, '__pycache__')
            try:
                shutil.rmtree(cache_path)
                print(f"   Deleted: {cache_path}")
                deleted_count += 1
            except Exception as e:
                print(f"   Failed: {cache_path} ({e})")
    
    print("\n2. Clearing workspace .numba_cache directories...")
    for root, dirs, files in os.walk('.'):
        if '.numba_cache' in dirs:
            cache_path = os.path.join(root, '.numba_cache')
            try:
                shutil.rmtree(cache_path)
                print(f"   Deleted: {cache_path}")
                deleted_count += 1
            except Exception as e:
                print(f"   Failed: {cache_path} ({e})")
    
    print("\n3. Clearing all .pyc files in workspace...")
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.pyc') or file.endswith('.pyo'):
                pyc_path = os.path.join(root, file)
                try:
                    os.remove(pyc_path)
                    print(f"   Deleted: {pyc_path}")
                    deleted_count += 1
                except Exception as e:
                    print(f"   Failed: {pyc_path} ({e})")
    
    print("\n4. Clearing user-level Numba cache...")
    # Numba stores cache in user's temp directory
    user_cache_dirs = [
        os.path.join(tempfile.gettempdir(), '__numba_cache__'),
        os.path.expanduser('~/.numba_cache'),
        os.path.expanduser('~/.cache/numba'),
    ]
    for cache_dir in user_cache_dirs:
        if os.path.exists(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                print(f"   Deleted: {cache_dir}")
                deleted_count += 1
            except Exception as e:
                print(f"   Failed: {cache_dir} ({e})")
    
    print("\n5. Clearing Python site-packages __pycache__...")
    try:
        import site
        for site_dir in site.getsitepackages():
            pycache_pattern = os.path.join(site_dir, '**', '__pycache__')
            for cache_path in glob.glob(pycache_pattern, recursive=True):
                try:
                    shutil.rmtree(cache_path)
                    print(f"   Deleted: {cache_path}")
                    deleted_count += 1
                except Exception as e:
                    pass  # Don't spam errors for system files
    except Exception as e:
        print(f"   Skipped site-packages (permission issue)")
    
    print("\n6. Clearing sys.modules cache...")
    if hasattr(sys, 'modules'):
        modules_to_clear = [m for m in list(sys.modules.keys()) 
                           if any(x in m.lower() for x in ['tradingalgo', 'numba', 'plotfigure', 'backtest'])]
        for mod in modules_to_clear:
            try:
                del sys.modules[mod]
            except:
                pass
        if modules_to_clear:
            print(f"   Cleared {len(modules_to_clear)} modules from memory")
    
    print("\n7. Clearing importlib cache...")
    try:
        import importlib
        importlib.invalidate_caches()
        print("   Invalidated importlib caches")
    except Exception as e:
        print(f"   Failed: {e}")
    
    print(f"\n{'='*80}")
    print(f"TOTAL ITEMS DELETED: {deleted_count}")
    print(f"{'='*80}")
    print("ALL CACHES CLEARED - Numba will recompile on next run")
    return deleted_count

if __name__ == "__main__":
    print("="*80)
    print("NUCLEAR CACHE CLEAR - DELETING ALL PYTHON/NUMBA CACHES")
    print("="*80)
    deleted = clear_numba_cache()
    print("\nDone. Run your script now - Numba will recompile fresh.")
