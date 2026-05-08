import matplotlib.pyplot as plt
import numpy as np

def plot_stats(sim, filename):
    """Plot statistics for all players: gold, health, and moves in separate subplots."""
    num_players = len(sim._players)
    
    # Use matplotlib's default color cycle to match the video trails
    prop_cycle = plt.rcParams['axes.prop_cycle']
    colors = prop_cycle.by_key()['color']
    colors = colors * (num_players // len(colors) + 1)  # repeat if more players than colors
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    # Plot gold
    for pId in range(num_players):
        axes[0].plot(sim.stats[pId]['gold'], label=sim._players[pId].player_name, 
                     color=colors[pId], linewidth=2)
    axes[0].set_title('Gold per Round', fontsize=14, weight='bold')
    axes[0].set_xlabel('Round')
    axes[0].set_ylabel('Gold')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Plot health
    for pId in range(num_players):
        axes[1].plot(sim.stats[pId]['health'], label=sim._players[pId].player_name, 
                     color=colors[pId], linewidth=2)
    axes[1].set_title('Health per Round', fontsize=14, weight='bold')
    axes[1].set_xlabel('Round')
    axes[1].set_ylabel('Health')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    
    # Plot moves
    for pId in range(num_players):
        axes[2].plot(sim.stats[pId]['moves'], label=sim._players[pId].player_name, 
                     color=colors[pId], linewidth=2)
    axes[2].set_title('Successful Moves per Round', fontsize=14, weight='bold')
    axes[2].set_xlabel('Round')
    axes[2].set_ylabel('Moves')
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=100)
    print(f"Statistics saved to {filename}")