"""
Smoke tests for _init_solver() and _board_to_bitboard()
Commit: test: add smoke tests for solver init and board conversion
"""

import sys
import os

# Allow importing from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import _init_solver, _board_to_bitboard

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_board():
    """Return a flat 6×7 board (row-major) filled with zeros."""
    return [0] * 42


def _make_board(positions):
    """
    Build a flat 6×7 board from a list of (row, col, mark) tuples.
    row 0 = top, row 5 = bottom (standard Connect-4 display order).
    """
    board = _empty_board()
    for row, col, mark in positions:
        board[row * 7 + col] = mark
    return board


# ---------------------------------------------------------------------------
# _init_solver() smoke tests
# ---------------------------------------------------------------------------

class TestInitSolver:

    def test_returns_non_none(self):
        """_init_solver() must return something (lib handle or 'FALLBACK')."""
        result = _init_solver()
        assert result is not None, "_init_solver() returned None"

    def test_idempotent(self):
        """Calling _init_solver() twice must return the same object."""
        first  = _init_solver()
        second = _init_solver()
        assert first is second, "_init_solver() is not idempotent (returned different objects)"

    def test_returns_lib_or_fallback(self):
        """
        The return value must either be the string 'FALLBACK' (compilation
        unavailable) or a ctypes CDLL-like object that exposes
        solve_kaggle_direct.
        """
        import ctypes
        lib = _init_solver()
        if lib == "FALLBACK":
            return  # acceptable – compiler not available in this environment
        assert hasattr(lib, "solve_kaggle_direct"), (
            "_init_solver() returned an object without solve_kaggle_direct"
        )

    def test_lib_function_callable_if_not_fallback(self):
        """
        If compilation succeeded, solve_kaggle_direct must be callable
        (not raise on attribute access).
        """
        lib = _init_solver()
        if lib == "FALLBACK":
            return
        fn = lib.solve_kaggle_direct
        assert callable(fn), "solve_kaggle_direct is not callable"


# ---------------------------------------------------------------------------
# _board_to_bitboard() smoke tests
# ---------------------------------------------------------------------------

class TestBoardToBitboard:

    # --- empty board -------------------------------------------------------

    def test_empty_board_both_zero(self):
        """An empty board must produce (cur=0, mask=0) for any mark."""
        cur, mask = _board_to_bitboard(_empty_board(), my_mark=1)
        assert cur  == 0, f"cur={cur}, expected 0 on empty board"
        assert mask == 0, f"mask={mask}, expected 0 on empty board"

    # --- single-piece boards -----------------------------------------------

    def test_single_own_piece_bottom_left(self):
        """
        One own piece at the bottom-left cell (row 5, col 0) must set
        exactly one bit in both cur and mask.
        """
        board = _make_board([(5, 0, 1)])
        cur, mask = _board_to_bitboard(board, my_mark=1)
        assert cur  != 0, "cur should be non-zero for own piece"
        assert mask != 0, "mask should be non-zero for own piece"
        # cur and mask must agree on this single piece
        assert cur == mask, "cur and mask must match for a single own piece"
        # Exactly one bit set
        assert bin(cur).count("1") == 1,  "exactly one bit expected in cur"
        assert bin(mask).count("1") == 1, "exactly one bit expected in mask"

    def test_single_opponent_piece(self):
        """
        One opponent piece must appear in mask but NOT in cur.
        """
        board = _make_board([(5, 0, 2)])
        cur, mask = _board_to_bitboard(board, my_mark=1)
        assert cur  == 0,  "cur must be 0 when only opponent has a piece"
        assert mask != 0,  "mask must be non-zero when opponent has a piece"

    def test_own_and_opponent_piece(self):
        """
        One own piece + one opponent piece: mask has 2 bits, cur has 1 bit.
        """
        board = _make_board([(5, 0, 1), (5, 1, 2)])
        cur, mask = _board_to_bitboard(board, my_mark=1)
        assert bin(cur).count("1")  == 1, "cur should have exactly 1 bit"
        assert bin(mask).count("1") == 2, "mask should have exactly 2 bits"

    # --- mark symmetry -----------------------------------------------------

    def test_mark_symmetry(self):
        """
        Swapping my_mark between 1 and 2 on the same board should swap
        which bits end up in cur (mask must stay identical).
        """
        board = _make_board([(5, 0, 1), (5, 1, 2)])
        cur1, mask1 = _board_to_bitboard(board, my_mark=1)
        cur2, mask2 = _board_to_bitboard(board, my_mark=2)
        assert mask1 == mask2, "mask must be the same regardless of my_mark"
        assert cur1  != cur2,  "cur must differ when my_mark is swapped"
        # The two cur values together should cover the whole mask
        assert (cur1 | cur2) == mask1, "cur1 | cur2 must equal mask"

    # --- full column -------------------------------------------------------

    def test_full_column(self):
        """
        Filling column 3 (6 pieces, alternating marks) must produce
        mask with exactly 6 bits set in column 3's bit range (bits 21-26).
        """
        positions = [(row, 3, (row % 2) + 1) for row in range(6)]
        board = _make_board(positions)
        _, mask = _board_to_bitboard(board, my_mark=1)
        col3_bits = (mask >> (3 * 7)) & 0b111111   # 6 bits for column 3
        assert bin(col3_bits).count("1") == 6, (
            f"Expected 6 bits in column 3, got {bin(col3_bits).count('1')}"
        )

    # --- bit positions don't overlap between columns -----------------------

    def test_no_column_overlap(self):
        """
        Pieces in different columns must never share the same bit.
        """
        board = _make_board([(5, col, 1) for col in range(7)])
        cur, mask = _board_to_bitboard(board, my_mark=1)
        assert bin(mask).count("1") == 7, "7 pieces must produce 7 distinct bits"

    # --- cur is always a subset of mask ------------------------------------

    def test_cur_subset_of_mask(self):
        """
        cur must always be a bitwise subset of mask.
        """
        board = _make_board([
            (5, 0, 1), (5, 1, 2), (4, 0, 2),
            (3, 3, 1), (2, 6, 1), (1, 2, 2),
        ])
        cur, mask = _board_to_bitboard(board, my_mark=1)
        assert (cur & mask) == cur, "cur must be a subset of mask"

    # --- determinism -------------------------------------------------------

    def test_deterministic(self):
        """Same board + mark must always produce the same (cur, mask)."""
        board = _make_board([(5, 0, 1), (4, 0, 2), (3, 0, 1)])
        result_a = _board_to_bitboard(board, my_mark=1)
        result_b = _board_to_bitboard(board, my_mark=1)
        assert result_a == result_b, "_board_to_bitboard() is not deterministic"


# ---------------------------------------------------------------------------
# Entry point (plain runner – no pytest dependency required)
# ---------------------------------------------------------------------------

def _run_all():
    suites = [TestInitSolver, TestBoardToBitboard]
    passed = failed = 0
    for suite_cls in suites:
        suite = suite_cls()
        print(f"\n{'='*60}")
        print(f"  {suite_cls.__name__}")
        print(f"{'='*60}")
        for name in [m for m in dir(suite_cls) if m.startswith("test_")]:
            try:
                getattr(suite, name)()
                print(f"  [PASS]  {name}")
                passed += 1
            except Exception as exc:
                print(f"  [FAIL]  {name}")
                print(f"          {exc}")
                failed += 1
    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'='*60}\n")
    return failed == 0


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
