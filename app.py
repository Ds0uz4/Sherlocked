import gradio as gr
import random
from collections import defaultdict

# ---------------- RADAR ----------------
RADAR_ENCODING = {
    "EMPTY": 0,
    "WALL": 1,
    "GOAL": 2,
    "ICE": 3,
    "MUD": 4,
    "DANGER": 5,
    "CHARGER": 6,
    "ENEMY": 7
}

# ---------------- ENV ----------------
class MegaWorldEnv:
    def __init__(self):
        self.start = (1, 1)
        self.goal = (18, 18)

        self.walls = self._generate_walls()
        self.ice = [(5,y) for y in range(5,15)] + [(15,y) for y in range(5,15)]
        self.mud = [(x,10) for x in range(2,18)]

        self.traps = [(3,3), (8,8), (12,12), (17,17), (9,10), (11,10)]
        random.shuffle(self.traps)

        self.chargers = [(18,2), (10,10)]

        self.enemies = [
            {"pos": [5, 5]},
            {"pos": [15, 5]},
            {"pos": [12, 12]},
            {"pos": [16, 16]},
            {"pos": [8, 14]}
        ]

    def _generate_walls(self):
        walls = []
        for i in range(20):
            if i % 4 == 0:
                for j in range(5, 15):
                    walls.append((i, j))
        walls += [(6,6), (7,7), (13,13), (14,14)]
        return walls

    def shaped_reward(self, old_pos, new_pos):
        old_d = abs(old_pos[0]-self.goal[0]) + abs(old_pos[1]-self.goal[1])
        new_d = abs(new_pos[0]-self.goal[0]) + abs(new_pos[1]-self.goal[1])
        return 3.0 * (old_d - new_d)

    def get_radar(self, pos):
        x, y = pos
        radar = {}
        dirs = {"up":(x,y+1),"down":(x,y-1),"left":(x-1,y),"right":(x+1,y)}

        for d,(nx,ny) in dirs.items():
            info = "EMPTY"
            if not (0<=nx<20 and 0<=ny<20): info="WALL"
            elif (nx,ny) in self.walls: info="WALL"
            elif (nx,ny)==self.goal: info="GOAL"
            elif (nx,ny) in self.ice: info="ICE"
            elif (nx,ny) in self.mud: info="MUD"
            elif (nx,ny) in self.traps: info="DANGER"
            elif (nx,ny) in self.chargers: info="CHARGER"
            for e in self.enemies:
                if tuple(e["pos"])==(nx,ny):
                    info="ENEMY"
            radar[d]=RADAR_ENCODING[info]
        return radar

    def update_enemies(self):
        for e in self.enemies:
            x,y = e["pos"]
            moves=[]
            for nx,ny in [(x,y+1),(x,y-1),(x-1,y),(x+1,y)]:
                if 0<=nx<20 and 0<=ny<20 and (nx,ny) not in self.walls:
                    moves.append((nx,ny))
            if moves:
                e["pos"]=list(random.choice(moves))

    def render(self, player_pos, history, battery, score):
        html = "<div style='background:#000;padding:10px;border-radius:10px;font-family:monospace'>"
        html += f"<div style='color:white'>🔋 {battery}% | 🏆 {score:.1f}</div>"
        html += "<div style='display:grid;grid-template-columns:repeat(20,22px);gap:1px'>"

        enemy_pos = [tuple(e["pos"]) for e in self.enemies]

        for y in range(19,-1,-1):
            for x in range(20):
                pos=(x,y)
                color="#111"; char=""
                if pos in self.walls: color="#555"
                elif pos in self.ice: color="#29b6f6"
                elif pos in self.mud: color="#4e342e"
                elif pos in history: color="#263238"
                if pos==self.goal: char="🏁"; color="#4caf50"
                if pos in self.chargers: char="⚡"; color="#fdd835"
                if pos in enemy_pos: char="👾"; color="#d500f9"
                if pos==player_pos:
                    char="🤖"
                    color="#2196f3" if battery>20 else "#ff6f00"
                html += f"<div style='width:22px;height:22px;background:{color};display:flex;align-items:center;justify-content:center'>{char}</div>"
        html += "</div></div>"
        return html

# ---------------- SAFE AGENT ----------------
def safe_agent_action(pos, radar, battery):
    """
    Simple greedy agent toward goal.
    No dynamic code execution (Spaces-safe).
    """
    preferences = [0,3,1,2]  # up, right, down, left
    for a in preferences:
        if list(radar.values())[a] not in (RADAR_ENCODING["WALL"], RADAR_ENCODING["ENEMY"]):
            return a
    return random.randint(0,3)

# ---------------- SIM ----------------
def run_mega_simulation():
    env = MegaWorldEnv()
    pos=list(env.start)
    battery=100
    score=0
    history=[]

    for step in range(300):
        radar=env.get_radar(pos)
        action=safe_agent_action(pos, radar, battery)

        dx,dy=[(0,1),(0,-1),(-1,0),(1,0)][action]
        prev=pos[:]
        nx,ny=pos[0]+dx,pos[1]+dy
        if not (0<=nx<20 and 0<=ny<20) or (nx,ny) in env.walls:
            nx,ny=pos
        pos=[nx,ny]

        env.update_enemies()
        history.append(tuple(pos))
        battery-=1
        if tuple(pos) in env.mud: battery-=5

        reward=env.shaped_reward(tuple(prev),tuple(pos))
        if prev==pos: reward-=5
        if tuple(pos) in env.traps: reward-=10; battery-=10

        done=False
        if battery<=0 or tuple(pos) in [tuple(e["pos"]) for e in env.enemies]:
            reward-=20; done=True
        if tuple(pos)==env.goal:
            reward+=1000; done=True

        reward=max(reward,-10)
        score+=reward

        yield env.render(tuple(pos),history,battery,score), {
            "step":step,
            "reward":round(reward,2),
            "battery":battery
        }

        if done:
            return

# ---------------- UI ----------------
with gr.Blocks() as demo:
    gr.Markdown("# 🌍 Super RL World (Spaces Safe)")
    game=gr.HTML()
    log=gr.JSON()
    btn=gr.Button("🚀 Run Simulation")
    btn.click(run_mega_simulation, outputs=[game,log])

demo.launch()
