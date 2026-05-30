# ─── Constants & implementations (mirror từ C++ trong main.py) ───────────────

WIDTH  = 7
HEIGHT = 6


def alignment(pos: int) -> bool:
    """Mirror của Position::alignment() trong C++."""
    m = pos & (pos << 7)
    if m & (m << 14): return True
    m = pos & (pos << 6)
    if m & (m << 12): return True
    m = pos & (pos << 8)
    if m & (m << 16): return True
    m = pos & (pos << 1)
    if m & (m <<  2): return True
    return False


def _board_mask() -> int:
    m = 0
    for c in range(WIDTH):
        m |= (63 << (c * 7))
    return m


def compute_winning_position(pos: int, mask: int) -> int:
    """Mirror của Position::compute_winning_position() trong C++."""
    H1, H2 = HEIGHT + 1, HEIGHT + 2
    r = (pos << 1) & (pos << 2) & (pos << 3)

    p = (pos << H1) & (pos << (2 * H1))
    r |= p & (pos << (3 * H1)); r |= p & (pos >> H1)
    p >>= 3 * H1
    r |= p & (pos << H1);       r |= p & (pos >> (3 * H1))

    p = (pos << HEIGHT) & (pos << (2 * HEIGHT))
    r |= p & (pos << (3 * HEIGHT)); r |= p & (pos >> HEIGHT)
    p >>= 3 * HEIGHT
    r |= p & (pos << HEIGHT);       r |= p & (pos >> (3 * HEIGHT))

    p = (pos << H2) & (pos << (2 * H2))
    r |= p & (pos << (3 * H2)); r |= p & (pos >> H2)
    p >>= 3 * H2
    r |= p & (pos << H2);       r |= p & (pos >> (3 * H2))

    return r & (_board_mask() ^ mask)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def bit(col: int, row: int) -> int:
    return 1 << (col * 7 + row)

def place_pieces(moves):
    """
    Dựng bitboard từ chuỗi nước đi theo gravity.
    moves: list[(col, player)]  player ∈ {1, 2}
    Trả về (bb_player1, bb_player2, mask).
    """
    heights = [0] * WIDTH
    bb = [0, 0]
    for col, player in moves:
        row = heights[col]
        assert row < HEIGHT, f"Cột {col} đã đầy"
        bb[player - 1] |= 1 << (col * 7 + row)
        heights[col] += 1
    return bb[0], bb[1], bb[0] | bb[1]


# ══════════════════════════════════════════════════════════════════════════════
# NHÓM 1 — alignment()
# ══════════════════════════════════════════════════════════════════════════════

class TestAlignment:

    def test_empty_board(self):
        assert alignment(0) is False

    def test_single_piece(self):
        assert alignment(bit(3, 2)) is False

    # ── Dọc ──────────────────────────────────────────────────────────────────

    def test_vertical_4_col0(self):
        pos = bit(0, 0) | bit(0, 1) | bit(0, 2) | bit(0, 3)
        assert alignment(pos) is True

    def test_vertical_4_top_col6(self):
        pos = bit(6, 2) | bit(6, 3) | bit(6, 4) | bit(6, 5)
        assert alignment(pos) is True

    def test_vertical_3_not_win(self):
        pos = bit(0, 0) | bit(0, 1) | bit(0, 2)
        assert alignment(pos) is False

    # ── Ngang ─────────────────────────────────────────────────────────────────

    def test_horizontal_4_row0(self):
        pos = bit(0, 0) | bit(1, 0) | bit(2, 0) | bit(3, 0)
        assert alignment(pos) is True

    def test_horizontal_4_row5(self):
        pos = bit(3, 5) | bit(4, 5) | bit(5, 5) | bit(6, 5)
        assert alignment(pos) is True

    def test_horizontal_3_not_win(self):
        pos = bit(0, 0) | bit(1, 0) | bit(2, 0)
        assert alignment(pos) is False

    def test_horizontal_gap_not_win(self):
        pos = bit(0, 0) | bit(1, 0) | bit(3, 0) | bit(4, 0)
        assert alignment(pos) is False

    # ── Chéo / ────────────────────────────────────────────────────────────────

    def test_diagonal_slash(self):
        pos = bit(0, 0) | bit(1, 1) | bit(2, 2) | bit(3, 3)
        assert alignment(pos) is True

    def test_diagonal_slash_shifted(self):
        pos = bit(2, 0) | bit(3, 1) | bit(4, 2) | bit(5, 3)
        assert alignment(pos) is True

    def test_diagonal_slash_3_not_win(self):
        pos = bit(0, 0) | bit(1, 1) | bit(2, 2)
        assert alignment(pos) is False

    # ── Chéo \ ────────────────────────────────────────────────────────────────

    def test_diagonal_backslash(self):
        pos = bit(0, 3) | bit(1, 2) | bit(2, 1) | bit(3, 0)
        assert alignment(pos) is True

    def test_diagonal_backslash_high(self):
        pos = bit(2, 5) | bit(3, 4) | bit(4, 3) | bit(5, 2)
        assert alignment(pos) is True

    def test_diagonal_backslash_3_not_win(self):
        pos = bit(0, 3) | bit(1, 2) | bit(2, 1)
        assert alignment(pos) is False

    # ── Rải rác ───────────────────────────────────────────────────────────────

    def test_scattered_no_alignment(self):
        pos = bit(0, 0) | bit(2, 2) | bit(4, 1) | bit(6, 5)
        assert alignment(pos) is False

    def test_two_separate_threes_no_alignment(self):
        pos = bit(0, 0) | bit(1, 0) | bit(2, 0) | bit(4, 0) | bit(5, 0) | bit(6, 0)
        assert alignment(pos) is False


# ══════════════════════════════════════════════════════════════════════════════
# NHÓM 2 — compute_winning_position()
# ══════════════════════════════════════════════════════════════════════════════

class TestComputeWinningPosition:

    # ── Dọc ──────────────────────────────────────────────────────────────────

    def test_vertical_win_cell(self):
        pos  = bit(0, 0) | bit(0, 1) | bit(0, 2)
        win  = compute_winning_position(pos, pos)
        assert win == bit(0, 3)

    def test_vertical_blocked(self):
        pos  = bit(0, 0) | bit(0, 1) | bit(0, 2)
        mask = pos | bit(0, 3)
        win  = compute_winning_position(pos, mask)
        assert not (win & bit(0, 3))

    def test_vertical_center_col(self):
        pos  = bit(3, 0) | bit(3, 1) | bit(3, 2)
        win  = compute_winning_position(pos, pos)
        assert win & bit(3, 3)

    # ── Ngang ─────────────────────────────────────────────────────────────────

    def test_horizontal_right_end(self):
        pos  = bit(0, 0) | bit(1, 0) | bit(2, 0)
        win  = compute_winning_position(pos, pos)
        assert win & bit(3, 0)

    def test_horizontal_left_end(self):
        pos  = bit(4, 0) | bit(5, 0) | bit(6, 0)
        win  = compute_winning_position(pos, pos)
        assert win & bit(3, 0)

    def test_horizontal_inner_both_ends(self):
        pos  = bit(1, 0) | bit(2, 0) | bit(3, 0)
        win  = compute_winning_position(pos, pos)
        assert win & bit(0, 0)
        assert win & bit(4, 0)

    def test_horizontal_blocked_one_end(self):
        pos  = bit(0, 0) | bit(1, 0) | bit(2, 0)
        mask = pos | bit(3, 0)
        win  = compute_winning_position(pos, mask)
        assert not (win & bit(3, 0))

    def test_horizontal_row3(self):
        pos  = bit(2, 3) | bit(3, 3) | bit(4, 3)
        win  = compute_winning_position(pos, pos)
        assert win & bit(1, 3)
        assert win & bit(5, 3)

    # ── Chéo / ────────────────────────────────────────────────────────────────

    def test_diagonal_slash_top_right(self):
        pos  = bit(0, 0) | bit(1, 1) | bit(2, 2)
        win  = compute_winning_position(pos, pos)
        assert win & bit(3, 3)

    def test_diagonal_slash_bottom_left(self):
        pos  = bit(1, 1) | bit(2, 2) | bit(3, 3)
        win  = compute_winning_position(pos, pos)
        assert win & bit(0, 0)

    # ── Chéo \ ────────────────────────────────────────────────────────────────

    def test_diagonal_backslash_win(self):
        pos  = bit(0, 3) | bit(1, 2) | bit(2, 1)
        win  = compute_winning_position(pos, pos)
        assert win & bit(3, 0)

    def test_diagonal_backslash_other_end(self):
        pos  = bit(1, 2) | bit(2, 1) | bit(3, 0)
        win  = compute_winning_position(pos, pos)
        assert win & bit(0, 3)

    # ── An toàn bitboard ──────────────────────────────────────────────────────

    def test_win_not_in_mask(self):
        pos  = bit(0, 0) | bit(0, 1) | bit(0, 2)
        mask = pos | bit(0, 3)
        win  = compute_winning_position(pos, mask)
        assert (win & mask) == 0

    def test_win_within_board(self):
        pos  = bit(0, 0) | bit(0, 1) | bit(0, 2)
        win  = compute_winning_position(pos, pos)
        assert (win & ~_board_mask()) == 0

    def test_full_column_no_out_of_board(self):
        pos = 0
        for row in range(HEIGHT):
            pos |= bit(0, row)
        win = compute_winning_position(pos, pos)
        assert (win & ~_board_mask()) == 0

    def test_win_no_overlap_with_opponent(self):
        pos  = bit(1, 0) | bit(2, 0) | bit(3, 0)
        mask = pos | bit(4, 0) | bit(5, 0)
        win  = compute_winning_position(pos, mask)
        assert (win & mask) == 0


# ══════════════════════════════════════════════════════════════════════════════
# NHÓM 3 — Thế cờ thực tế
# ══════════════════════════════════════════════════════════════════════════════

class TestRealGamePositions:

    def test_p1_wins_vertical_center(self):
        bb1, bb2, _ = place_pieces([
            (3, 1), (0, 2),
            (3, 1), (0, 2),
            (3, 1), (0, 2),
            (3, 1),
        ])
        assert alignment(bb1) is True
        assert alignment(bb2) is False

    def test_p1_wins_horizontal_row0(self):
        bb1, bb2, _ = place_pieces([
            (0, 1), (0, 2),
            (1, 1), (1, 2),
            (2, 1), (2, 2),
            (3, 1),
        ])
        assert alignment(bb1) is True
        assert alignment(bb2) is False

    def test_p1_wins_diagonal_slash(self):
        bb1, _, _ = place_pieces([
            (0, 1),
            (1, 2), (1, 1),
            (2, 2), (2, 2), (2, 1),
            (3, 2), (3, 2), (3, 2), (3, 1),
        ])
        assert alignment(bb1) is True

    def test_p2_can_win_next_move(self):
        pos  = bit(6, 0) | bit(6, 1) | bit(6, 2)
        mask = pos | bit(0, 0) | bit(0, 1)
        win  = compute_winning_position(pos, mask)
        assert win & bit(6, 3)

    def test_full_board_mask(self):
        moves = [
            (col, 1 if (col + row) % 2 == 0 else 2)
            for col in range(WIDTH)
            for row in range(HEIGHT)
        ]
        _, _, mask = place_pieces(moves)
        assert mask == _board_mask()