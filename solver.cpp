
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
