import gradio as gr
import importlib.util
import time
import random
import os
import sys
import shutil
import zipfile
import tempfile
import uuid

# --- MEGA WORLD CLASS (SERVER VERSION) ---
RADAR_ENCODING = {"EMPTY": 0,"WALL": 1,"GOAL": 2,"ICE": 3,"MUD": 4,"DANGER": 5,"CHARGER": 6,"ENEMY": 7}

class MegaWorldEnv:
    def __init__(self):
        self.start = (1, 1)
        # CHANGE 1: Goal moved to absolute top right (19, 19)
        self.goal = (19, 19) 
        self.walls = self._generate_walls()
        self.ice = [(5,y) for y in range(5,15)] + [(15,y) for y in range(5,15)]
        self.mud = [(x,10) for x in range(2,18)]
        self.traps = [(3,3),(8,8),(12,12),(17,17),(9,10),(11,10)]; random.shuffle(self.traps)
        self.chargers = [(18,2),(10,10)]
        self.enemies = [{"pos":[5,5],"type":"patrol","axis":"x","range":(5,10),"dir":1},{"pos":[15,5],"type":"patrol","axis":"x","range":(12,17),"dir":1},{"pos":[12,12],"type":"hunter", "step": 0}, {"pos":[16,16],"type":"hunter", "step": 0}]
        random.shuffle(self.enemies)

    def _generate_walls(self):
        walls = []
        for y in range(20): 
            if y not in [3, 16]: walls.append((9, y))
        for x in range(20): 
            if x not in [3, 16]: walls.append((x, 9))
        walls.extend([(4,4), (4,5), (4,6), (5,4), (6,4), (14,4), (14,5), (14,6), (15,4), (16,4), (4,14), (4,15), (4,16), (5,14), (6,14)])
        for i in range(15, 19): walls.append((i, 15))
        walls.extend([(14,14), (13,13)])
        return walls

    # *** ENABLED SHAPED REWARD HERE ***
    def shaped_reward(self, old_pos, new_pos):
        old_dist = abs(old_pos[0]-self.goal[0]) + abs(old_pos[1]-self.goal[1])
        new_dist = abs(new_pos[0]-self.goal[0]) + abs(new_pos[1]-self.goal[1])
        return 3.0 * (old_dist - new_dist)

    def get_radar(self, pos):
        x,y=pos; radar={}
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
                e["pos"][0]+=e["dir"]; nx = e["pos"][0]
                if nx>=e["range"][1] or nx<=e["range"][0] or (nx, e["pos"][1]) in self.walls:
                    e["dir"]*=-1; e["pos"][0]+=e["dir"]
            else:
                path = [(1,0), (1,0), (0,1), (0,1), (-1,0), (-1,0), (0,-1), (0,-1)]
                move = path[e["step"] % len(path)]
                nx, ny = e["pos"][0] + move[0], e["pos"][1] + move[1]
                if (nx, ny) not in self.walls and 0<=nx<20 and 0<=ny<20: e["pos"]=[nx,ny]
                e["step"] += 1

    def render(self, player_pos, history, battery, score):
        # HTML Visualizer
        html="<div style='background:#000;padding:10px;border-radius:12px;font-family:monospace'>"
        html+=f"<div style='color:white;margin-bottom:5px'>🔋 {battery} | 🏆 {score:.1f}</div>" 
        html+="<div style='display:grid;grid-template-columns:repeat(20,20px);gap:1px;width:fit-content;margin:auto'>"
        enemy_pos=[tuple(e["pos"]) for e in self.enemies]
        for y in range(19,-1,-1):
            for x in range(20):
                pos=(x,y); color="#111"; char=""
                if pos in self.walls: color="#555"
                elif pos in self.ice: color="#29b6f6"
                elif pos in self.mud: color="#4e342e"
                elif pos in history: color="#263238"
                if pos==self.goal: char="🏁"; color="#4caf50"
                if pos in self.chargers: char="⚡"; color="#fdd835"
                if pos in enemy_pos: char="👹"; color="#d500f9"
                if pos==player_pos: char="🤖"; color="#2196f3" if battery>20 else "#ff6f00"
                html+=f"<div style='width:20px;height:20px;background:{color};display:flex;align-items:center;justify-content:center;font-size:12px'>{char}</div>"
        html+="</div></div>"
        return html

# ---------------------------------------------------------
# SERVER CONFIG
# ---------------------------------------------------------
FLAG = "CTF{r3w4rd_sh4p1ng_1s_th3_k3y}"

def run_mega_simulation(zip_file):
    env = MegaWorldEnv()
    
    if zip_file is None:
        yield env.render(env.start, [], 100, 0), {"status": "Waiting for upload..."}
        return

    # Setup Temp Directory
    run_id = str(uuid.uuid4())
    temp_dir = os.path.join(tempfile.gettempdir(), "ctf_run_" + run_id)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # Extract Zip
        try:
            with zipfile.ZipFile(zip_file.name, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        except Exception as e:
            yield env.render(env.start, [], 0, 0), {"error": f"Invalid Zip: {e}"}
            return

        # Load Agent
        agent_path = os.path.join(temp_dir, "agent.py")
        if not os.path.exists(agent_path):
            yield env.render(env.start, [], 0, 0), {"error": "agent.py not found!"}
            return

        sys.path.append(temp_dir)
        
        try:
            spec = importlib.util.spec_from_file_location("agent_module", agent_path)
            agent = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(agent)
        except Exception as e:
            yield env.render(env.start, [], 0, 0), {"error": f"Code Error: {e}"}
            return

        # Run Simulation
        pos = list(env.start)
        battery = 100
        score = 0
        history = []
        
        for step in range(1000):
            radar = env.get_radar(pos)
            
            try:
                action = agent.get_action(tuple(pos), radar, battery)
                if action not in [0, 1, 2, 3]: action = 0
            except Exception as e:
                yield env.render(tuple(pos), history, 0, score), {"error": f"Runtime Error: {e}"}
                break

            dx, dy = [(0,1), (0,-1), (-1,0), (1,0)][action]
            prev_pos = pos[:]
            nx, ny = pos[0]+dx, pos[1]+dy
            
            # Wall Collision
            if not (0 <= nx < 20 and 0 <= ny < 20) or (nx, ny) in env.walls:
                nx, ny = pos
            pos = [nx, ny]

            # *** APPLY SHAPED REWARD ***
            step_reward = env.shaped_reward(tuple(prev_pos), tuple(pos))
            score += step_reward

            env.update_enemies(pos)
            history.append(tuple(pos))
            battery -= 1
            if tuple(pos) in env.mud: battery -= 5
            
            # Win
            if tuple(pos) == env.goal:
                score += 1000
                yield env.render(tuple(pos), history, battery, score), {"RESULT": f"VICTORY! {FLAG}"}
                break
            
            # Loss
            enemy_pos = [tuple(e["pos"]) for e in env.enemies]
            if battery <= 0:
                yield env.render(tuple(pos), history, 0, score), {"RESULT": "DIED: Battery Empty"}
                break
            if tuple(pos) in enemy_pos:
                yield env.render(tuple(pos), history, 0, score), {"RESULT": "DIED: Caught by Enemy"}
                break
            if tuple(pos) in env.traps:
                battery -= 10 

            # Render
            yield env.render(tuple(pos), history, battery, score), {"step": step}
            
            # CHANGE 2: Slower speed (0.15s delay per frame)
            time.sleep(0.15) 

    finally:
        if temp_dir in sys.path:
            sys.path.remove(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

with gr.Blocks(theme=gr.themes.Monochrome()) as demo:
    gr.Markdown("# 🚩 CTF: The Fortress Run")
    gr.Markdown("Upload `solution.zip` to run your agent.")
    with gr.Row():
        game = gr.HTML(MegaWorldEnv().render((1,1), [], 100, 0))
        with gr.Column():
            file_input = gr.File(label="Upload Submission (.zip)", file_types=[".zip"])
            run_btn = gr.Button("Deploy Agent", variant="primary")
            logs = gr.JSON(label="Status")
    run_btn.click(run_mega_simulation, file_input, [game, logs])

if __name__ == "__main__":
    demo.launch()
# --- TRAINING SCRIPT SNIPPET FOR REFERENCE ---