def test_rolling():
    D = [10, 20, 30, 40, 50]
    P = 3
    w = 0.8
    
    # Naive
    print("NAIVE:")
    for t in range(len(D)):
        start = max(0, t - P + 1)
        sub = D[start:t+1]
        s = 0
        current_w = 1.0
        for val in reversed(sub):
            s += val * current_w
            current_w *= w
        print(f"t={t}, {sub} -> {s}")
        
    print("\nO(1):")
    S = 0
    w_p = w ** P
    for t in range(len(D)):
        val = D[t]
        S = val + w * S
        if t >= P:
            dropped = D[t-P]
            S -= dropped * w_p
        print(f"t={t}, -> {S}")

test_rolling()
