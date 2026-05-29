"""
test_solver.py
==============
Kiểm tra kết nối thư viện C++ solver (Connect Four) qua ctypes.

Cách chạy:
    python test_solver.py

Yêu cầu: g++ (>= C++17) có trong PATH.
"""

import os
import subprocess
import ctypes
import time
import sys

# ──────────────────────────────────────────────────────────────────────────────
# 1.  NẠP THƯ VIỆN C++
# ──────────────────────────────────────────────────────────────────────────────

_CPP_SOURCE = r"""
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


def load_solver() -> ctypes.CDLL:
    """Biên dịch C++ và nạp shared library. Hoạt động trên cả Windows lẫn Linux/Mac."""
    import tempfile, platform

    tmp_dir  = tempfile.gettempdir()          # C:\Users\...\AppData\Local\Temp  hoặc /tmp
    ts       = int(time.time())
    src_path = os.path.join(tmp_dir, "c4_solver_test.cpp")

    is_windows = platform.system() == "Windows"
    lib_ext    = ".dll" if is_windows else ".so"
    lib_path   = os.path.join(tmp_dir, f"c4_solver_test_{ts}{lib_ext}")

    with open(src_path, "w", encoding="utf-8") as f:
        f.write(_CPP_SOURCE)

    # -fPIC không cần/không hợp lệ trên Windows
    compile_cmd = ["g++", "-O3", "-shared", "-std=c++17", src_path, "-o", lib_path]
    if not is_windows:
        compile_cmd.insert(3, "-fPIC")
    else:
        compile_cmd += ["-static-libgcc", "-static-libstdc++"]

    result = subprocess.run(compile_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Biên dịch thất bại:\n{result.stderr}")

    abs_lib = os.path.abspath(lib_path)
    if is_windows:
        os.add_dll_directory(os.path.dirname(abs_lib))
        for mingw_dir in [r"C:\mingw64\bin", r"C:\msys64\mingw64\bin",
                          r"C:\Program Files\mingw-w64\bin"]:
            if os.path.exists(mingw_dir):
                os.add_dll_directory(mingw_dir)
                break
        lib = ctypes.CDLL(abs_lib, winmode=0)
    else:
        lib = ctypes.CDLL(abs_lib)

    lib.solve_kaggle_direct.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
    lib.solve_kaggle_direct.restype  = ctypes.c_int
    return lib


# ──────────────────────────────────────────────────────────────────────────────
# 2.  HÀM TIỆN ÍCH: CHUYỂN BOARD → BITBOARD
# ──────────────────────────────────────────────────────────────────────────────

def board_to_bitboard(board: list[int], my_mark: int) -> tuple[int, int]:
    """
    board  : list 42 phần tử, chỉ số [row*7 + col], row 0 = trên cùng.
             0 = ô trống, 1 = người chơi 1, 2 = người chơi 2.
    my_mark: 1 hoặc 2 – quân của người chơi hiện tại.

    Trả về (current_position, mask) theo quy ước bitboard của solver:
      - Bit (col*7 + row_from_bottom) biểu diễn ô (col, row_from_bottom).
      - row_from_bottom = 0 là đáy, 5 là đỉnh.
    """
    cur = mask = 0
    for col in range(7):
        bit = col * 7
        for row in range(5, -1, -1):          # row 5 (đỉnh giao diện) → bit thấp
            val = board[row * 7 + col]
            if val:
                mask |= (1 << bit)
                if val == my_mark:
                    cur |= (1 << bit)
            bit += 1
    return cur, mask


def render_board(board: list[int]) -> str:
    """Vẽ bàn cờ ra terminal."""
    sym = {0: ".", 1: "X", 2: "O"}
    lines = []
    for row in range(6):
        lines.append(" ".join(sym[board[row * 7 + col]] for col in range(7)))
    lines.append("0 1 2 3 4 5 6")   # chỉ số cột (0-indexed)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 3.  CÁC TEST CASE
# ──────────────────────────────────────────────────────────────────────────────

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

def run_test(lib, name: str, board: list[int], my_mark: int,
             expected_cols: list[int] | None) -> bool:
    """
    Gọi solver và kiểm tra kết quả.

    expected_cols : danh sách cột hợp lệ (None = chỉ kiểm tra solver không crash
                   và trả về cột trong [0,6]).
    """
    cur, mask = board_to_bitboard(board, my_mark)
    t0  = time.perf_counter()
    col = lib.solve_kaggle_direct(cur, mask)
    dt  = (time.perf_counter() - t0) * 1000

    ok = (0 <= col <= 6) and (expected_cols is None or col in expected_cols)
    status = PASS if ok else FAIL

    print(f"\n{'─'*60}")
    print(f"[{status}] {name}")
    print(render_board(board))
    print(f"  Người chơi : {my_mark}  |  cur=0x{cur:016X}  mask=0x{mask:016X}")
    print(f"  Solver trả về cột : {col}  (mong đợi: {expected_cols})  [{dt:.1f} ms]")
    return ok


def make_empty_board() -> list[int]:
    return [0] * 42


def place(board: list[int], col: int, mark: int) -> list[int]:
    """Đặt quân vào cột (tìm hàng thấp nhất còn trống từ đáy lên)."""
    b = board[:]
    for row in range(5, -1, -1):
        if b[row * 7 + col] == 0:
            b[row * 7 + col] = mark
            return b
    raise ValueError(f"Cột {col} đã đầy")


# ──────────────────────────────────────────────────────────────────────────────
# 3a. Bàn cờ trống → solver phải chọn cột giữa (3) vì đó là nước khai cuộc tối ưu
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_board(lib) -> bool:
    board = make_empty_board()
    return run_test(lib, "Bàn cờ trống – khai cuộc tối ưu là cột 3",
                    board, my_mark=1, expected_cols=[3])


# ──────────────────────────────────────────────────────────────────────────────
# 3b. Người chơi 1 có 3 quân nằm ngang, cần chặn/thắng ngay cột 4
#     Bố cục (hàng 5 = đáy):
#       hàng 5: X X X . . . .   → đánh vào cột 3 để thắng
# ──────────────────────────────────────────────────────────────────────────────

def test_win_horizontal(lib) -> bool:
    board = make_empty_board()
    # X ở cột 0, 1, 2 (hàng đáy = row index 5)
    board = place(board, 0, 1)
    board = place(board, 1, 1)
    board = place(board, 2, 1)
    # O đặt ngẫu nhiên chỗ khác (row 5, col 5) để mask không trống
    board = place(board, 5, 2)
    return run_test(lib, "Thắng ngang tức thì – X phải đánh cột 3",
                    board, my_mark=1, expected_cols=[3])


# ──────────────────────────────────────────────────────────────────────────────
# 3c. Người chơi 2 có 3 quân dọc, người chơi 1 PHẢI chặn ở cột 4
#     Bố cục: O ở cột 4, hàng 5/4/3; đến lượt X (mark=1)
# ──────────────────────────────────────────────────────────────────────────────

def test_block_vertical(lib) -> bool:
    """
    Bố cục (row 5 = đáy, row 0 = đỉnh):

        . . . . . . .
        . . . . . . .
        . . . . . . .
        . . . . O . .   ← row 2  (O hàng 3 từ đáy)
        . . . . O . .   ← row 3  (O hàng 2 từ đáy)
        X X X . O . .   ← row 5 (đáy)  (O hàng 1 từ đáy)

    O có 3 quân dọc ở cột 4 (rows 5/4/3 = hàng 1/2/3 từ đáy).
    Đến lượt X (mark=1) – bắt buộc chặn tại cột 4 (hàng 4 từ đáy).

    Lưu ý: vì game bắt đầu từ 0 nước, solver nhận đây là lượt của
    người có mark=1. Ta truyền trực tiếp bitboard thủ công.
    """
    # Tạo bitboard thủ công thay vì dùng place() để tránh lỗi thứ tự lượt.
    # Quy ước: bit = col*7 + row_from_bottom  (row_from_bottom 0 = đáy).
    # O (mark 2) ở cột 4, các hàng 0, 1, 2 từ đáy:
    o_bits = [(4 * 7 + 0), (4 * 7 + 1), (4 * 7 + 2)]
    # X (mark 1) ở cột 0, 1, 2 hàng đáy (row_from_bottom = 0):
    x_bits = [(0 * 7 + 0), (1 * 7 + 0), (2 * 7 + 0)]

    cur = 0   # X = current player
    mask = 0
    for b in x_bits:
        cur  |= (1 << b)
        mask |= (1 << b)
    for b in o_bits:
        mask |= (1 << b)   # O không thuộc cur

    # Vẽ board để hiển thị
    board = [0] * 42
    for b in x_bits:
        col_b = b // 7
        rfb   = b % 7         # row_from_bottom
        row   = 5 - rfb       # row 0 = đỉnh
        board[row * 7 + col_b] = 1
    for b in o_bits:
        col_b = b // 7
        rfb   = b % 7
        row   = 5 - rfb
        board[row * 7 + col_b] = 2

    # Gọi solver với bitboard đã tính sẵn
    t0  = time.perf_counter()
    col = lib.solve_kaggle_direct(cur, mask)
    dt  = (time.perf_counter() - t0) * 1000

    # Thế này X cũng thắng ngay tại cột 3 (4 ngang), solver ưu tiên thắng > chặn
    expected = [3, 4]
    ok = col in expected
    status = PASS if ok else FAIL

    print(f"\n{'─'*60}")
    print(f"[{status}] Thắng/chặn – X đánh cột 3 (thắng ngay) hoặc cột 4 (chặn O dọc)")
    print(render_board(board))
    print(f"  Người chơi : 1  |  cur=0x{cur:016X}  mask=0x{mask:016X}")
    print(f"  Solver trả về cột : {col}  (mong đợi: {expected})  [{dt:.1f} ms]")
    return ok


# ──────────────────────────────────────────────────────────────────────────────
# 3d. Người chơi 1 có thể thắng chéo – đánh vào cột tạo chéo hoàn chỉnh
#     Thế chéo: X ở (col=0,row5), (col=1,row4), (col=2,row3) → thắng tại col 3
# ──────────────────────────────────────────────────────────────────────────────

def test_win_diagonal(lib) -> bool:
    board = make_empty_board()
    # Đặt "đế" cho chéo
    board = place(board, 1, 2)   # O hàng 5, col 1
    board = place(board, 2, 2)   # O hàng 5, col 2
    board = place(board, 2, 2)   # O hàng 4, col 2  (chồng thêm)
    board = place(board, 3, 2)   # O hàng 5, col 3
    board = place(board, 3, 2)   # O hàng 4, col 3
    board = place(board, 3, 2)   # O hàng 3, col 3
    # X theo đường chéo tăng dần
    board = place(board, 0, 1)   # X tại hàng 5, col 0
    board = place(board, 1, 1)   # X tại hàng 4, col 1
    board = place(board, 2, 1)   # X tại hàng 3, col 2
    # Đến lượt X: thắng chéo tại col 3 (hàng 2)
    return run_test(lib, "Thắng chéo – X phải đánh cột 3",
                    board, my_mark=1, expected_cols=[3])


# ──────────────────────────────────────────────────────────────────────────────
# 3e. Bàn cờ gần đầy (stress test) – solver không được crash, trả về cột hợp lệ
# ──────────────────────────────────────────────────────────────────────────────

def test_nearly_full_board(lib) -> bool:
    """
    Tạo bàn cờ xen kẽ X/O không có ai thắng, chỉ còn 1 ô trống ở cột 6.
    Solver phải trả về đúng cột 6.
    """
    # Điền theo thứ tự cột 0‥5 đầy, cột 6 để trống 1 ô
    # Xen kẽ mark để không ai thắng
    board = make_empty_board()
    move_num = 0
    for col in range(6):           # 6 cột đầu, mỗi cột 6 ô
        for _ in range(6):
            mark = 1 + (move_num % 2)
            board = place(board, col, mark)
            move_num += 1
    # Cột 6: điền 5 ô, để 1 ô trống
    for i in range(5):
        mark = 1 + (move_num % 2)
        board = place(board, 6, mark)
        move_num += 1

    current_mark = 1 + (move_num % 2)
    return run_test(lib, "Bàn cờ gần đầy – chỉ còn cột 6",
                    board, my_mark=current_mark, expected_cols=[6])


# ──────────────────────────────────────────────────────────────────────────────
# 4.  CHẠY TẤT CẢ TEST
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  TEST KẾT NỐI SOLVER C++ QUA CTYPES")
    print("=" * 60)

    # --- Bước 1: biên dịch & nạp thư viện ---
    print("\n[1/2] Biên dịch thư viện C++ ...", end=" ", flush=True)
    try:
        lib = load_solver()
        print("OK")
    except RuntimeError as e:
        print(f"THẤT BẠI\n{e}")
        sys.exit(1)

    # --- Bước 2: chạy các test case ---
    print("[2/2] Chạy test cases ...")
    tests = [
        test_empty_board,
        test_win_horizontal,
        test_block_vertical,
        test_win_diagonal,
        test_nearly_full_board,
    ]

    results = [t(lib) for t in tests]

    # --- Tổng kết ---
    passed = sum(results)
    total  = len(results)
    print(f"\n{'='*60}")
    print(f"KẾT QUẢ: {passed}/{total} test PASSED")
    if passed == total:
        print("\033[32mTất cả test đều vượt qua!\033[0m")
    else:
        failed = [tests[i].__name__ for i, r in enumerate(results) if not r]
        print(f"\033[31mCác test thất bại: {failed}\033[0m")
    print("=" * 60)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()