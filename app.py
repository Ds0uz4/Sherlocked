import gradio as gr
import importlib.util
import time
import random

# Encoding for the agent's radar
RADAR_ENCODING = {"EMPTY":0, "WALL":1, "GOAL":2, "ICE":3, "MUD":4, "DANGER":5, "CHARGER":6, "ENEMY":7}

class MegaWorldEnv:
    def __init__(self):
        self.start, self.goal = (1, 1), (18, 18)
        self.walls = self._generate_walls()
        self.traps = [(3,3),(8,8),(12,12),(17,17),(9,10),(11,10)]
        self.mud = [(x,10) for x in range(2,18)]
        # Enemies start at fixed positions
        self.enemies = [{"pos":[5,5]}, {"pos":[15,5]}, {"pos":[12,12]}, {"pos":[16,16]}]

    def _generate_walls(self):
        w = [(i,j) for i in range(0,20,4) for j in range(5,15)]
        w += [(6,6),(7,7),(13,13),(14,14)]
        return w

    def get_radar(self, pos):
        x, y = pos
        radar = {}
        for name, (nx, ny) in {"up":(x,y+1),"down":(x,y-1),"left":(x-1,y),"right":(x+1,y)}.items():
            if not (0<=nx<20 and 0<=ny<20) or (nx,ny) in self.walls: info="WALL"
            elif (nx,ny)==self.goal: info="GOAL"
            elif (nx,ny) in self.traps: info="DANGER"
            elif any(e["pos"]==[nx,ny] for e in self.enemies): info="ENEMY"
            elif (nx,ny) in self.mud: info="MUD"
            else: info="EMPTY"
            radar[name] = RADAR_ENCODING[info]
        return radar

    def update_enemies(self):
        # Random walk movement
        for e in self.enemies:
            moves = [(e["pos"][0]+dx, e["pos"][1]+dy) for dx,dy in [(0,1),(0,-1),(1,0),(-1,0)]]
            valid = [m for m in moves if 0<=m[0]<20 and 0<=m[1]<20 and m not in self.walls]
            if valid: e["pos"] = list(random.choice(valid))

    def render(self, p_pos, history, bat, score):
        # Optimized string-based rendering
        grid = ["<div style='background:#000;padding:5px;border-radius:10px;font-family:monospace;'>"]
        grid.append(f"<div style='color:#fff;'>🔋 {bat} | 🏆 {score:.1f}</div>")
        grid.append("<div style='display:grid;grid-template-columns:repeat(20,18px);gap:1px;'>")
        
        e_pos = [tuple(e["pos"]) for e in self.enemies]
        for y in range(19,-1,-1):
            for x in range(20):
                c = "#111"; char = ""
                if (x,y) in self.walls: c="#444"
                elif (x,y) == self.goal: c="#2e7d32"; char="🏁"
                elif (x,y) in e_pos: c="#c62828"; char="👾"
                elif (x,y) == p_pos: c="#1565c0"; char="🤖"
                grid.append(f"<div style='width:18px;height:18px;background:{c};display:flex;justify-content:center;align-items:center;font-size:12px;'>{char}</div>")
        grid.append("</div></div>")
        return "".join(grid)

def run_sim(file):
    env = MegaWorldEnv()
    if not file: yield env.render(env.start,[],100,0), "Please upload Agent.py"
    
    spec = importlib.util.spec_from_file_location("agent", file.name)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    
    # Run pre-training if the agent supports it
    if hasattr(agent, "train"): agent.train(env)
    
    pos, bat, score, hist = list(env.start), 100, 0, []
    for s in range(300):
        radar = env.get_radar(pos)
        action = agent.get_action(pos, radar, bat)
        dx, dy = [(0,1),(0,-1),(-1,0),(1,0)][action]
        
        old_pos = tuple(pos)
        nx, ny = pos[0]+dx, pos[1]+dy
        if 0<=nx<20 and 0<=ny<20 and (nx,ny) not in env.walls: pos = [nx,ny]
        
        env.update_enemies()
        bat -= (5 if tuple(pos) in env.mud else 1)
        
        # Reward shaping: Distance to goal
        reward = (abs(old_pos[0]-18)+abs(old_pos[1]-18)) - (abs(pos[0]-18)+abs(pos[1]-18))
        
        if tuple(pos)==env.goal: 
            reward+=1000; score+=1000
            yield env.render(tuple(pos),hist,bat,score), "🎉 SUCCESS!"
            return
        if any(e["pos"]==pos for e in env.enemies) or bat<=0:
            yield env.render(tuple(pos),hist,0,score), "💀 MISSION FAILED"
            return
        
        if hasattr(agent, "observe"): agent.observe(reward, pos, radar, bat, False)
        score += reward
        yield env.render(tuple(pos),hist,bat,score), f"Step {s}"
        time.sleep(0.05)

with gr.Blocks(css=".gradio-container {background-color: #111}") as demo:
    gr.Markdown("# 💀 Super RL World: Chaos Edition")
    with gr.Row():
        board = gr.HTML(MegaWorldEnv().render((1,1),[],100,0))
        with gr.Column():
            in_file = gr.File(label="Upload Agent.py")
            run_btn = gr.Button("🚀 Start Run", variant="primary")
            txt = gr.Textbox(label="Mission Log")
    run_btn.click(run_sim, in_file, [board, txt])

demo.launch()