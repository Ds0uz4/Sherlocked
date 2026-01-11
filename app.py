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

        # 1. NEW MAZE STRUCTURE
        self.walls = self._generate_walls()
        
        # 2. Hazards
        self.ice = [(5,y) for y in range(5,15)] + [(15,y) for y in range(5,15)]
        self.mud = [(x,10) for x in range(2,18)]
        
        # Traps (Randomized locations)
        self.traps = [(3,3),(8,8),(12,12),(17,17),(9,10),(11,10)]
        random.shuffle(self.traps)

        # Chargers
        self.chargers = [(18,2),(10,10)] 
        
        # Enemies
        # We ensure they spawn in valid locations for the new map
        self.enemies = [
            {"pos":[5,5],"type":"patrol","axis":"x","range":(5,10),"dir":1},
            {"pos":[15,5],"type":"patrol","axis":"x","range":(12,17),"dir":1},
            {"pos":[12,12],"type":"hunter", "step": 0}, 
            {"pos":[16,16],"type":"hunter", "step": 0}
        ]
        random.shuffle(self.enemies)

    def _generate_walls(self):
        """
        New Layout: 'The Fortress'
        A 4-chamber maze with central walls and narrow choke points.
        """
        walls = []
        
        # --- 1. The Great Cross (Divides map into 4 quadrants) ---
        # Vertical central wall (x=9)
        for y in range(20):
            if y not in [3, 16]: # Gaps at y=3 and y=16
                walls.append((9, y))
                
        # Horizontal central wall (y=9)
        for x in range(20):
            if x not in [3, 16]: # Gaps at x=3 and x=16
                walls.append((x, 9))

        # --- 2. Quadrant Obstacles (Clutter) ---
        # Top-Left Room (Start Zone)
        walls.extend([(4,4), (4,5), (4,6), (5,4), (6,4)])
        
        # Top-Right Room (Patrol Zone)
        walls.extend([(14,4), (14,5), (14,6), (15,4), (16,4)])
        
        # Bottom-Left Room (Mud Zone)
        walls.extend([(4,14), (4,15), (4,16), (5,14), (6,14)])
        
        # Bottom-Right Room (Goal Zone) - The 'Bunker'
        # Protective casing around the goal area to force specific entry
        for i in range(15, 19):
            walls.append((i, 15)) # Bar above goal area
            
        walls.extend([(14,14), (13,13)]) # Extra clutter
        
        return walls

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
                # Basic bounce check against walls/map edge
                nx = e["pos"][0]
                if nx>=e["range"][1] or nx<=e["range"][0] or (nx, e["pos"][1]) in self.walls:
                    e["dir"]*=-1
                    e["pos"][0]+=e["dir"] # Step back
            else:
                # DESIGNATED MOVEMENT: Square Patrol
                path = [(1,0), (1,0), (0,1), (0,1), (-1,0), (-1,0), (0,-1), (0,-1)]
                move = path[e["step"] % len(path)]
                
                nx, ny = e["pos"][0] + move[0], e["pos"][1] + move[1]
                
                # Only move if not hitting a wall (simple collision check)
                if (nx, ny) not in self.walls and 0<=nx<20 and 0<=ny<20:
                    e["pos"][0] = nx
                    e["pos"][1] = ny
                    
                e["step"] += 1

    def render(self, player_pos, history, battery, score):
        html="<div style='background:#000;padding:10px;border-radius:12px'>"
        html+=f"<div style='color:white'>🔋 {battery} | 🏆 {score:.1f}</div>"
        html+="<div style='display:grid;grid-template-columns:repeat(20,22px);gap:1px'>"
        enemy_pos=[tuple(e["pos"]) for e in self.enemies]
        for y in range(19,-1,-1):
            for x in range(20):
                pos=(x,y)
                color="#111"; char=""
                if pos in self.walls: color="#555" # Grey Walls
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
    battery=2000
    score=0
    history=[]

    for step in range(3000):
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
    gr.Markdown("# Super RL World — FORTRESS EDITION")
    with gr.Row():
        game=gr.HTML(MegaWorldEnv().render((1,1),[],100,0))
        with gr.Column():
            file=gr.File(label="Upload agent.py")
            btn=gr.Button("Run")
            log=gr.JSON()
    btn.click(run_mega_simulation,file,[game,log])

demo.launch()