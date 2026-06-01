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
    void clear()                        { std::fill(K, K+SIZE, 0); std::fill(V, V+SIZE, 0); }
    void put(uint64_t key, uint8_t val) { size_t i=key%SIZE; K[i]=key; V[i]=val; }
    uint8_t get(uint64_t key)        const { size_t i=key%SIZE; return K[i]==key ? V[i] : 0; }
};

static TranspositionTable transTable;
static bool         g_timeout = false;
static unsigned int g_nodes   = 0;
static const int    COL_ORDER[] = {3, 2, 4, 1, 5, 0, 6};
static std::chrono::steady_clock::time_point g_start;

int negamax(const Position &P, int alpha, int beta) {
    if (g_timeout) return 0;
    if ((++g_nodes & 16383) == 0) {
        if (std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - g_start).count() > 1900)
            { g_timeout = true; return 0; }
    }

    if (P.nbMoves() == WIDTH * HEIGHT) return 0;
    for (int col = 0; col < WIDTH; ++col)
        if (P.canPlay(col) && (P.compute_winning_position(P.current_position, P.mask) & P.possible() & Position::column_mask(col)))
            return (WIDTH * HEIGHT + 1 - P.nbMoves()) / 2;

    const uint64_t key = P.key();
    int min_score = Position::MIN_SCORE, max_score = Position::MAX_SCORE;
    if (int val = transTable.get(key)) {
        if (val > Position::MAX_SCORE - Position::MIN_SCORE + 1) {
            min_score = val + 2*Position::MIN_SCORE - Position::MAX_SCORE - 2;
            if (alpha < min_score) { alpha = min_score; if (alpha >= beta) return alpha; }
        } else {
            max_score = val + Position::MIN_SCORE - 1;
            if (beta > max_score) { beta = max_score; if (alpha >= beta) return beta; }
        }
    }

    uint64_t possible_mask = P.possibleNonLosingMoves();
    if (possible_mask == 0) return -(WIDTH * HEIGHT - P.nbMoves()) / 2;

    MoveSorter moves;
    for (int i = 0; i < WIDTH; ++i) {
        uint64_t move = possible_mask & Position::column_mask(COL_ORDER[i]);
        if (move) moves.add(move, P.moveScore(move));
    }

    while (uint64_t next = moves.getNext()) {
        Position P2(P); P2.play(next);
        int score = -negamax(P2, -beta, -alpha);
        if (score >= beta) { transTable.put(key, score + Position::MAX_SCORE - 2*Position::MIN_SCORE + 2); return score; }
        if (score > alpha) alpha = score;
    }
    transTable.put(key, alpha - Position::MIN_SCORE + 1);
    return alpha;
}

int solve(const Position &P) {
    int lo = -(WIDTH*HEIGHT - P.nbMoves()) / 2;
    int hi =  (WIDTH*HEIGHT + 1 - P.nbMoves()) / 2;
    while (lo < hi) {
        int med = lo + (hi - lo) / 2;
        if      (med <= 0 && lo/2 < med) med = lo/2;
        else if (med >= 0 && hi/2 > med) med = hi/2;
        int r = negamax(P, med, med+1);
        if (r <= med) hi = r; else lo = r;
    }
    return lo;
}

extern "C" {
    int solve_kaggle_direct(uint64_t current_position, uint64_t mask) {
        Position P;
        P.current_position = current_position;
        P.mask = mask;
        g_timeout = false; g_nodes = 0;
        g_start = std::chrono::steady_clock::now();
        transTable.clear();

        for (int col = 0; col < WIDTH; ++col) {
            if (P.canPlay(col)) {
                Position P2(P); P2.playCol(col);
                if (P.alignment(P2.mask ^ P2.current_position)) return col;
            }
        }

        int best_col = -1, best_score = -9999;
        for (int i = 0; i < WIDTH; ++i)
            if (P.canPlay(COL_ORDER[i])) { best_col = COL_ORDER[i]; break; }

        for (int i = 0; i < WIDTH; ++i) {
            int col = COL_ORDER[i];
            if (P.canPlay(col)) {
                Position P2(P); P2.playCol(col);
                int score = -solve(P2);
                if (g_timeout) return best_col;
                if (score > best_score) {
                    best_score = score; best_col = col;
                    if (score > 0) return best_col;
                }
            }
        }
        return best_col;
    }
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

# PART 2: PYTHON HEURISTIC SEARCH ENGINE

ROWS, COLS = 6, 7
H, H1 = 6, 7
INF, WIN_SCORE = 10_000_000, 1_000_000
COL_ORDER = [3, 2, 4, 1, 5, 0, 6]

ZOBRIST = [[[random.getrandbits(64) for _ in range(2)] for _ in range(ROWS)] for _ in range(COLS)]
HISTORY = [[[0 for _ in range(2)] for _ in range(ROWS)] for _ in range(COLS)]
KILLERS = [[-1, -1] for _ in range(42)]
TT_SIZE = 1048576  # 2^20
TT_K = [0] * TT_SIZE
TT_V = [0] * TT_SIZE

def _is_win(pos):
    m = pos & (pos >> 7)
    if m & (m >> 14): return True
    m = pos & (pos >> 6)
    if m & (m >> 12): return True
    m = pos & (pos >> 8)
    if m & (m >> 16): return True
    m = pos & (pos >> 1)
    if m & (m >> 2): return True
    return False

def _negamax(pos, mask, depth, alpha, beta, ply, turn_color, z_key):
    global TT_K, TT_V, KILLERS, HISTORY, ZOBRIST, INF, WIN_SCORE

    if _is_win(pos ^ mask):
        return -(WIN_SCORE - ply)

    if bin(mask).count('1') == 42:
        return 0

    if depth == 0:
        return 0

    tt_idx = z_key % TT_SIZE
    tt_entry = TT_V[tt_idx]
    
    if TT_K[tt_idx] == z_key and tt_entry != 0:
        tt_depth, tt_flag, tt_val, tt_move = tt_entry
        if tt_depth >= depth:
            if tt_flag == 0:
                return tt_val
            elif tt_flag == 1:
                alpha = max(alpha, tt_val)
            elif tt_flag == 2:
                beta = min(beta, tt_val)
            if alpha >= beta:
                return tt_val

    moves = []
    for col in COL_ORDER:
        top_mask = 1 << (5 + col * 7)
        if (mask & top_mask) == 0:
            score = 0
            if KILLERS[ply][0] == col:
                score += 900000
            elif KILLERS[ply][1] == col:
                score += 800000
            else:
                row = ((mask + (1 << (col * 7))) ^ mask).bit_length() - 1 - (col * 7)
                score += HISTORY[col][row][turn_color]
            moves.append((score, col))

    moves.sort(key=lambda x: x[0], reverse=True)

    best_val = -INF
    best_move = -1
    orig_alpha = alpha

    for _, col in moves:
        new_mask = mask | (mask + (1 << (col * 7)))
        new_pos = pos ^ mask
        row = (new_mask ^ mask).bit_length() - 1 - (col * 7)
        new_z_key = z_key ^ ZOBRIST[col][row][turn_color]
        
        val = -_negamax(new_pos, new_mask, depth - 1, -beta, -alpha, ply + 1, 1 - turn_color, new_z_key)

        if val > best_val:
            best_val = val
            best_move = col

        alpha = max(alpha, val)
        if alpha >= beta:
            if KILLERS[ply][0] != col:
                KILLERS[ply][1] = KILLERS[ply][0]
                KILLERS[ply][0] = col
            HISTORY[col][row][turn_color] += depth * depth
            break

    flag = 0
    if best_val <= orig_alpha:
        flag = 2
    elif best_val >= beta:
        flag = 1
        
    TT_K[tt_idx] = z_key
    TT_V[tt_idx] = (depth, flag, best_val, best_move)

    return best_val

def _search(pos, mask, max_depth, turn_color, z_key, start_time, time_limit):
    global INF, TT_K, TT_V, TT_SIZE
    
    best_move = COL_ORDER[0]
    last_score = 0
    
    for depth in range(1, max_depth + 1):
        if time.time() - start_time > time_limit:
            break
            
        if depth < 3:
            alpha = -INF
            beta = INF
        else:
            alpha = last_score - 50
            beta = last_score + 50
            
        while True:
            score = _negamax(pos, mask, depth, alpha, beta, 0, turn_color, z_key)
            
            if time.time() - start_time > time_limit:
                break
                
            if score <= alpha:
                alpha = -INF
            elif score >= beta:
                beta = INF
            else:
                last_score = score
                break
                
        tt_idx = z_key % TT_SIZE
        if TT_K[tt_idx] == z_key and TT_V[tt_idx] != 0:
            tt_move = TT_V[tt_idx][3]
            if tt_move != -1:
                best_move = tt_move
                
    return best_move

def _get_v4_params(board, my_mark):
    pos = mask = zh = 0
    for kr in range(6):
        our_r = 5 - kr
        for c in range(7):
            cell = board[kr*7 + c]
            if cell:
                bit = 1 << (c*7 + our_r)
                mask |= bit
                if cell == my_mark: pos |= bit
                zh ^= ZOBRIST[cell-1][c][our_r]
    return pos, mask, zh