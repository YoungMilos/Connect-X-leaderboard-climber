from kaggle_environments import make, evaluate

env = make("connectx", debug=True)

my_agent_file = "main.py"

opponent = "random" 

p1_wins = p2_wins = draws = 0

for i in range(10):
    # Agent là P2
    env.reset()
    env.run([opponent, my_agent_file])
    result = env.state[1].reward
    if result == 1:
        p2_wins += 1
    elif result == -1:
        p1_wins += 1
    else:
        draws += 1

print(f"Agent (P2): {p2_wins}W / {p1_wins}L / {draws}D vs Random")

html_output = env.render(mode="html")
with open("replay.html", "w") as f:
    f.write(html_output)
print("Đã lưu video ván đấu vào file 'replay.html'. Hãy mở file này bằng trình duyệt web!")