import gradio as gr
import importlib.util
import time
import random
from collections import defaultdict

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

class MegaWorldEnv:
    def __init__(self):
        self.start = (1, 1)
        self.goal = (18, 18)

        self.walls = self._generate_walls()
        self.ice = [(5,y) for y in range(5,15)] + [(15,y) for y in range(5,15)]
        self.mud = [(x,10) for x in range(2,18)]
        self.traps = [(3,3),(8,8),(12,12),(17,17),(9,10),(11,10)]
        random.shuffle(self.traps)

        self.chargers = [(2,18),(18,2),(10,10)]
        self.enemies = [
            {"pos":[5,5],"type":"patrol","axis":"x","range":(5,10),"dir":1},
            {"pos":[15,5],"type":"patrol","axis":"x","range":(12,17),"dir":1},
            {"pos":[12,12],"type":"hunter"},
            {"pos":[16,16],"type":"hunter"}
        ]
        random.shuffle(self.enemies)

    def _generate_walls(self):
        walls=[]
        for i in range(20):
            if i%4==0:
                for j in range(5,15):
                    walls.append((i,j))
        walls += [(6,6),(7,7),(13,13),(14,14)]
        return walls

    # 🔑 STRONG SHAPING
    def shaped_reward(self, old_pos, new_pos):
        old_d = abs(old_pos[0]-self.goal[0]) + abs(old_pos[1]-self.goal[1])
        new_d = abs(new_pos[0]-self.goal[0]) + abs(new_pos[1]-self.goal[1])
        return 3.0 * (old_d - new_d)

    def get_radar(self, pos):
        x,y=pos
        radar={}
        dirs={"up":(x,y+1),"down":(x,y-1),"left":(x-1,y),"right":(x+1,y)}
        for d,(nx,ny) in dirs.items():
            info="EMPTY"
            if not (0<=nx<20 and 0<=ny<20): info="WALL"
            elif (nx,ny) in self.walls: info="WALL"
            elif (nx,ny)==self.goal: info="GOAL"
            elif (nx,ny) in self.ice: info="ICE"
            elif (nx,ny) in self.mud: info="MUD"
            elif (nx,ny) in self.traps: info="DANGER"
            elif (nx,ny) in self.chargers: info="CHARGER"
            for e in self.enemies:
                if tuple(e["pos"])==(nx,ny): info="ENEMY"
            radar[d]=RADAR_ENCODING[info]
        return radar

    def update_enemies(self, player_pos):
        for e in self.enemies:
            if e["type"]=="patrol":
                e["pos"][0]+=e["dir"]
                if e["pos"][0]>=e["range"][1] or e["pos"][0]<=e["range"][0]:
                    e["dir"]*=-1
            else:
                d=abs(e["pos"][0]-player_pos[0])+abs(e["pos"][1]-player_pos[1])
                if d<6 and random.random()<0.85:
                    dx=player_pos[0]-e["pos"][0]
                    dy=player_pos[1]-e["pos"][1]
                    if abs(dx)>abs(dy): e["pos"][0]+=1 if dx>0 else -1
                    else: e["pos"][1]+=1 if dy>0 else -1

    def render(self, player_pos, history, battery, score):
        html="<div style='background:#000;padding:10px;border-radius:12px'>"
        html+=f"<div style='color:white'>🔋 {battery} | 🏆 {score:.1f}</div>"
        html+="<div style='display:grid;grid-template-columns:repeat(20,22px);gap:1px'>"
        enemy_pos=[tuple(e["pos"]) for e in self.enemies]
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
                if pos in enemy_pos: char="👹"; color="#d500f9"
                if pos==player_pos:
                    char="🤖"
                    color="#2196f3" if battery>20 else "#ff6f00"
                html+=f"<div style='width:22px;height:22px;background:{color};display:flex;align-items:center;justify-content:center'>{char}</div>"
        html+="</div></div>"
        return html

def run_mega_simulation(file):
    env=MegaWorldEnv()
    if file is None:
        yield env.render(env.start,[],100,0),{}
        return

    spec=importlib.util.spec_from_file_location("agent",file.name)
    agent=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)

    pos=list(env.start)
    battery=100
    score=0
    history=[]

    for step in range(300):
        radar=env.get_radar(pos)
        action=agent.get_action(pos[:],radar,battery)
        dx,dy=[(0,1),(0,-1),(-1,0),(1,0)][action]
        prev_pos=pos[:]

        nx,ny=pos[0]+dx,pos[1]+dy
        if not (0<=nx<20 and 0<=ny<20) or (nx,ny) in env.walls:
            nx,ny=pos
        pos=[nx,ny]

        env.update_enemies(pos)
        history.append(tuple(pos))

        battery-=1
        if tuple(pos) in env.mud: battery-=5

        reward=env.shaped_reward(tuple(prev_pos),tuple(pos))

        if prev_pos==pos: reward-=5
        if tuple(pos) in env.traps:
            reward-=10; battery-=10

        done=False
        if battery<=0 or tuple(pos) in [tuple(e["pos"]) for e in env.enemies]:
            reward-=20; done=True
        if tuple(pos)==env.goal:
            reward+=1000; done=True

        reward=max(reward,-10)
        score+=reward

        if hasattr(agent,"observe"):
            agent.observe(reward,pos,radar,battery,done)

        yield env.render(tuple(pos),history,battery,score),{"step":step,"reward":reward}

        if done: return
        time.sleep(0.05)

with gr.Blocks() as demo:
    gr.Markdown("# Super RL World — FINAL SOLVABLE VERSION")
    with gr.Row():
        game=gr.HTML(MegaWorldEnv().render((1,1),[],100,0))
        with gr.Column():
            file=gr.File(label="Upload agent.py")
            btn=gr.Button("Run")
            log=gr.JSON()
    btn.click(run_mega_simulation,file,[game,log])

demo.launch()
