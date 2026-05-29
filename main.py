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

    bool canWinNext() const {
        return (compute_winning_position(current_position, mask) & possible()) != 0;
    }

    uint64_t opponent_winning_position() const {
        return compute_winning_position(current_position ^ mask, mask);
    }

    uint64_t possibleNonLosingMoves() const {
        assert(!canWinNext());
        uint64_t possible_mask = possible();
        uint64_t opponent_win  = opponent_winning_position();
        uint64_t forced        = possible_mask & opponent_win;
        if (forced) {
            if (forced & (forced - 1)) return 0;
            possible_mask = forced;
        }
        return possible_mask & ~(opponent_win >> 1);
    }

    static uint64_t compute_winning_position(uint64_t pos, uint64_t mask) {
        uint64_t r = (pos << 1) & (pos << 2) & (pos << 3);
        uint64_t p;

        p = (pos << (HEIGHT+1)) & (pos << 2*(HEIGHT+1));
        r |= p & (pos << 3*(HEIGHT+1)); r |= p & (pos >> (HEIGHT+1));
        p >>= 3*(HEIGHT+1);
        r |= p & (pos << (HEIGHT+1));   r |= p & (pos >> 3*(HEIGHT+1));

        p = (pos << HEIGHT) & (pos << 2*HEIGHT);
        r |= p & (pos << 3*HEIGHT); r |= p & (pos >> HEIGHT);
        p >>= 3*HEIGHT;
        r |= p & (pos << HEIGHT);   r |= p & (pos >> 3*HEIGHT);

        p = (pos << (HEIGHT+2)) & (pos << 2*(HEIGHT+2));
        r |= p & (pos << 3*(HEIGHT+2)); r |= p & (pos >> (HEIGHT+2));
        p >>= 3*(HEIGHT+2);
        r |= p & (pos << (HEIGHT+2));   r |= p & (pos >> 3*(HEIGHT+2));

        return r & (board_mask() ^ mask);
    }

    int      moveScore(uint64_t move) const { return __builtin_popcountll(compute_winning_position(current_position | move, mask)); }
    uint64_t key()                    const { return current_position + mask; }
    
    static uint64_t top_mask(int col)    { return (uint64_t)1 << (5 + col * 7); }
    static uint64_t bottom_mask(int col) { return (uint64_t)1 << (col * 7); }
    static uint64_t column_mask(int col) { return ((uint64_t)63) << (col * 7); }
    static uint64_t bottom_mask_all() {
        uint64_t m = 0;
        for (int c = 0; c < WIDTH; ++c) m |= bottom_mask(c);
        return m;
    }
    static uint64_t board_mask() {
        uint64_t m = 0;
        for (int c = 0; c < WIDTH; ++c) m |= column_mask(c);
        return m;
    }
};

class MoveSorter {
public:
    unsigned int size;
    struct { uint64_t move; int score; } entries[WIDTH];

    MoveSorter() : size(0) {}
    void add(uint64_t move, int score) {
        int pos = size++;
        for (; pos && entries[pos-1].score > score; --pos) entries[pos] = entries[pos-1];
        entries[pos] = {move, score};
    }
    uint64_t getNext() { return size ? entries[--size].move : 0; }
};

class TranspositionTable {
    static const size_t SIZE = 16777259;
    uint64_t *K; uint8_t *V;
public:
    TranspositionTable()  { K = new uint64_t[SIZE](); V = new uint8_t[SIZE](); }
    ~TranspositionTable() { delete[] K; delete[] V; }
    void    clear()                        { std::fill(K, K+SIZE, 0); std::fill(V, V+SIZE, 0); }
    void    put(uint64_t key, uint8_t val) { size_t i=key%SIZE; K[i]=key; V[i]=val; }
    uint8_t get(uint64_t key)        const { size_t i=key%SIZE; return K[i]==key ? V[i] : 0; }
};

static TranspositionTable transTable;
static bool         g_timeout = false;
static unsigned int g_nodes   = 0;
static const int    COL_ORDER[] = {3, 2, 4, 1, 5, 0, 6};
static std::chrono::steady_clock::time_point g_start;

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

