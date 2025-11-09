import json
import random

def lambda_handler(event, context):
    path = event.get("rawPath") or event.get("path")
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

    if path == "/":
        return respond({
            "apiversion": "1",
            "author": "amanda",
            "color": "#5203fc",
            "head": "smart-caterpillar",
            "tail": "weight"
        })

    elif path == "/start" and method == "POST":
        return respond({})

    elif path == "/move" and method == "POST":
        body = json.loads(event.get("body", "{}"))
        move = choose_best_move(body)
        print(f"Selected move: {move}")
        return respond({"move": move})

    elif path == "/end" and method == "POST":
        return respond({})

    else:
        return {"statusCode": 404, "body": "Not found"}


def respond(body):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }


def choose_best_move(body):
    # Main decision logic for choosing the best move.
    # Addresses TODOs: avoid collisions and seek food when hungry.
    safe_moves = get_safe_moves(body)
    
    if not safe_moves:
        # No safe moves - just try anything as a fallback
        print("WARNING: No safe moves found!")
        return random.choice(["up", "down", "left", "right"])
    
    head = body["you"]["head"]
    health = body["you"]["health"]
    food_list = body["board"]["food"]
    board_width = body["board"]["width"]
    board_height = body["board"]["height"]
    
    # Get all obstacles for space evaluation
    obstacles = set()
    for snake in body["board"]["snakes"]:
        for segment in snake["body"]:
            obstacles.add((segment["x"], segment["y"]))
    
    # Evaluate available space for each move (avoid getting trapped)
    move_scores = []
    for move, nx, ny in safe_moves:
        space = evaluate_move_space(nx, ny, board_width, board_height, obstacles)
        move_scores.append((move, nx, ny, space))
    
    # Filter out moves with very little space (potential traps)
    min_acceptable_space = 5
    good_moves = [m for m in move_scores if m[3] >= min_acceptable_space]
    
    # If all moves look risky, use the least risky
    if not good_moves:
        good_moves = move_scores
    
    # If health is low, prioritize food
    if health < 30 and food_list:
        nearest_food = find_nearest_food(head["x"], head["y"], food_list)
        if nearest_food:
            food_move = get_move_toward_target(
                head["x"], head["y"], 
                nearest_food["x"], nearest_food["y"], 
                good_moves
            )
            if food_move:
                print(f"Low health ({health}), seeking food at ({nearest_food['x']}, {nearest_food['y']})")
                return food_move
    
    # Otherwise, choose move with most space to avoid getting trapped
    best_move = max(good_moves, key=lambda m: m[3])
    print(f"Choosing {best_move[0]} with {best_move[3]} available space")
    return best_move[0]


def get_safe_moves(body):
    # Determines safe moves avoiding walls, own body, and other snakes.
    # Returns a list of tuples: (move_name, x_coord, y_coord).
    board_width = body["board"]["width"]
    board_height = body["board"]["height"]
    head = body["you"]["head"]
    x, y = head["x"], head["y"]
    
    # Get all snake bodies (including yours)
    # Exclude the tail tip since it will move (unless snake just ate)
    all_snake_bodies = set()
    for snake in body["board"]["snakes"]:
        # Add all body segments except the tail
        for i, segment in enumerate(snake["body"]):
            if i < len(snake["body"]) - 1:  # Don't include tail
                all_snake_bodies.add((segment["x"], segment["y"]))
    
    # Possible moves
    moves = {
        "up": (x, y + 1),
        "down": (x, y - 1),
        "left": (x - 1, y),
        "right": (x + 1, y)
    }
    
    safe_moves = []
    for move, (nx, ny) in moves.items():
        # Check bounds
        if not (0 <= nx < board_width and 0 <= ny < board_height):
            print(f"  {move} -> out of bounds")
            continue
        
        # Check collisions with snake bodies
        if (nx, ny) in all_snake_bodies:
            print(f"  {move} -> collision with snake body")
            continue
        
        # Check risky head-to-head collisions with larger/equal snakes
        if is_risky_head_collision(nx, ny, body):
            print(f"  {move} -> risky head-to-head collision")
            continue
            
        safe_moves.append((move, nx, ny))
    
    print(f"Safe moves: {[m[0] for m in safe_moves]}")
    return safe_moves


def is_risky_head_collision(nx, ny, body):
    # Check if a move could result in a head-to-head collision with a larger or equal snake.
    my_length = len(body["you"]["body"])
    
    for snake in body["board"]["snakes"]:
        if snake["id"] == body["you"]["id"]:
            continue
        
        snake_head = snake["head"]
        snake_length = len(snake["body"])
        
        # Check if enemy snake could move to adjacent squares
        enemy_possible_moves = [
            (snake_head["x"] + 1, snake_head["y"]),
            (snake_head["x"] - 1, snake_head["y"]),
            (snake_head["x"], snake_head["y"] + 1),
            (snake_head["x"], snake_head["y"] - 1)
        ]
        
        # If our move puts us adjacent to a larger/equal snake head, it's risky
        if (nx, ny) in enemy_possible_moves and snake_length >= my_length:
            return True
    
    return False


def find_nearest_food(head_x, head_y, food_list):
    # Find the nearest food using Manhattan distance.
    if not food_list:
        return None
    
    nearest = None
    min_distance = float('inf')
    
    for food in food_list:
        distance = abs(food["x"] - head_x) + abs(food["y"] - head_y)
        if distance < min_distance:
            min_distance = distance
            nearest = food
    
    return nearest


def get_move_toward_target(head_x, head_y, target_x, target_y, move_options):
    # Choose the best move toward a target from the list of available moves.
    # move_options is a list of tuples: (move_name, x, y, space)
    best_move = None
    best_distance = float('inf')
    
    for move_info in move_options:
        move = move_info[0]
        nx = move_info[1]
        ny = move_info[2]
        
        distance = abs(target_x - nx) + abs(target_y - ny)
        if distance < best_distance:
            best_distance = distance
            best_move = move
    
    return best_move


def evaluate_move_space(nx, ny, board_width, board_height, obstacles):
    # Use flood fill to estimate available space from a position.
    # This helps avoid moves that trap the snake.
    visited = set()
    queue = [(nx, ny)]
    visited.add((nx, ny))
    space = 0
    max_iterations = 50  # Limit for performance in Lambda
    
    while queue and space < max_iterations:
        cx, cy = queue.pop(0)
        space += 1
        
        # Check all 4 directions
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            new_x, new_y = cx + dx, cy + dy
            
            if (0 <= new_x < board_width and 
                0 <= new_y < board_height and 
                (new_x, new_y) not in visited and 
                (new_x, new_y) not in obstacles):
                visited.add((new_x, new_y))
                queue.append((new_x, new_y))
    
    return space