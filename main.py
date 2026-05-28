import os
import subprocess
import ctypes
import random
import time
import array
import base64
import zlib
import json

# PART 1: C++ PERFECT SOLVER

_CPP_SOURCE = """
#include <cstdint>
#include <cassert>
#include <algorithm>
#include <chrono>

#define HEIGHT 6
#define WIDTH  7

class Position {
public:
    static const int MIN_SCORE = -(WIDTH * HEIGHT) / 2;
    static const int MAX_SCORE = (WIDTH * HEIGHT + 1) / 2;

    uint64_t current_position;
    uint64_t mask;

    Position() : current_position(0), mask(0) {}

    int      nbMoves()        const { return __builtin_popcountll(mask); }
    bool     canPlay(int col) const { return (mask & top_mask(col)) == 0; }
    void     play(uint64_t move)    { current_position ^= mask; mask |= move; }
    void     playCol(int col)       { play((mask + bottom_mask(col)) & column_mask(col)); }
    uint64_t possible()       const { return (mask + bottom_mask_all()) & board_mask(); }

    bool alignment(uint64_t pos) const {
        uint64_t m;
        m = pos & (pos << 7); if (m & (m << 14)) return true;
        m = pos & (pos << 6); if (m & (m << 12)) return true;
        m = pos & (pos << 8); if (m & (m << 16)) return true;
        m = pos & (pos << 1); if (m & (m <<  2)) return true;
        return false;
    }
"""

_solver_lib = None

def _init_solver():
    global _solver_lib
    if _solver_lib is not None:
        return _solver_lib
    src = "/tmp/solver.cpp"
    lib = f"/tmp/solver_{int(time.time())}.so"
    if os.name == "nt":
        src = "solver.cpp"
        lib = f"./solver_{int(time.time())}.dll"
    try:
        with open(src, "w", encoding="utf-8") as f:
            f.write(_CPP_SOURCE)
        flags = ["g++", "-O3", "-shared", "-fPIC", "-std=c++17"]
        if os.name == "nt":
            flags += ["-static-libgcc", "-static-libstdc++", "-static"]
        subprocess.run(flags + [src, "-o", lib], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        abs_lib = os.path.abspath(lib)
        if os.name == "nt":
            mingw = r"C:\mingw64\bin"
            if os.path.exists(mingw): os.add_dll_directory(mingw)
            os.add_dll_directory(os.path.dirname(abs_lib))
            _solver_lib = ctypes.CDLL(abs_lib, winmode=0)
        else:
            _solver_lib = ctypes.CDLL(abs_lib)
        _solver_lib.solve_kaggle_direct.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
        _solver_lib.solve_kaggle_direct.restype  = ctypes.c_int
    except Exception:
        _solver_lib = "FALLBACK"
    return _solver_lib

def _board_to_bitboard(board, my_mark):
    cur = mask = 0
    for col in range(7):
        bit = col * 7
        for row in range(5, -1, -1):
            val = board[row * 7 + col]
            if val:
                mask |= (1 << bit)
                if val == my_mark: cur |= (1 << bit)
            bit += 1
    return cur, mask