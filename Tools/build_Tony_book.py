import json, base64, zlib, random, time

ROWS, COLS = 6, 7
_rng = random.Random(0x5ca1a)
ZOBRIST = [[[_rng.getrandbits(64) for _ in range(ROWS)] for _ in range(COLS)] for _ in range(2)]

def compute_v4_hash_and_ply(state_str):
    clean_str = state_str.replace('[','').replace(']','').replace(',',' ').strip()
    digits = [int(x) for x in clean_str.split() if x.isdigit()]
    if len(digits) != 42:
        digits = [int(x) for x in state_str if x.isdigit()]
    if len(digits) != 42:
        return None, 0
    ply = sum(1 for x in digits if x != 0)
    zh = 0
    for kr in range(ROWS):
        our_r = (ROWS - 1) - kr
        for c in range(COLS):
            cell = digits[kr * COLS + c]
            if cell != 0:
                p_idx = cell - 1
                if 0 <= p_idx <= 1:
                    zh ^= ZOBRIST[p_idx][c][our_r]
    return zh, ply

INPUT_FILE = "tony_data.txt"
MAX_PLY = 12

book_dict = {}
line_count = 0
valid_count = 0

print(f"Bắt đầu quét '{INPUT_FILE}'...")
start_time = time.time()

def process_line(line_str, value_indices, state_idx, delimiter):
    global valid_count
    if not line_str:
        return
    row = line_str.split(delimiter) if delimiter else line_str.split()
    if len(row) <= max(value_indices):
        return
    state_str = row[state_idx]
    zh, ply = compute_v4_hash_and_ply(state_str)
    if zh is None or ply > MAX_PLY:
        return
    try:
        actions = [float(row[i]) for i in value_indices]
        clean_str = state_str.replace('[','').replace(']','').replace(',',' ').replace(' ','')
        CENTER_ORDER = [3, 2, 4, 1, 5, 0, 6]
        valid_actions = [(c, actions[c]) for c in CENTER_ORDER if clean_str[c] == '0']
        if valid_actions:
            current_player = ply % 2
            if current_player == 0:
                best_move = max(valid_actions, key=lambda x: x[1])[0]
            else:
                best_move = min(valid_actions, key=lambda x: x[1])[0]
            book_dict[str(zh)] = best_move
            valid_count += 1
    except (ValueError, IndexError):
        pass

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    first_line = f.readline()
    line_count += 1
    delimiter = "," if "," in first_line else None
    header = [h.strip().lower() for h in (first_line.split(delimiter) if delimiter else first_line.split())]

    state_idx = 0
    value_indices = []
    for idx, name in enumerate(header):
        if "state" in name or "board" in name:
            state_idx = idx
        if any(x in name for x in ["v","q","action","score"]) and any(str(i) in name for i in range(7)):
            value_indices.append(idx)
    if len(value_indices) < 7:
        value_indices = list(range(state_idx + 1, state_idx + 8))

    process_line(first_line.strip(), value_indices, state_idx, delimiter)

    for line in f:
        line_count += 1
        process_line(line.strip(), value_indices, state_idx, delimiter)

        if line_count % 200_000 == 0:
            elapsed = time.time() - start_time
            rate = line_count / elapsed if elapsed > 0 else 0
            print(f"  {line_count:,} dòng | {valid_count:,} thế | {rate/1000:.0f}k dòng/s")

print(f"\nHoàn tất: {line_count:,} dòng: {valid_count:,} thế cờ")
print("Đang nén...")
json_str = json.dumps(book_dict)
compressed_bytes = zlib.compress(json_str.encode('utf-8'), level=1)
b64_string = base64.b64encode(compressed_bytes).decode('utf-8')

with open("compressed_output.txt", "w") as f:
    f.write(f"COMPRESSED_BOOK = '{b64_string}'\n")

print(f"Done {len(b64_string)/1024:.2f} KB")