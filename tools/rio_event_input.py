# Rio PC/console input from a FRESH save: dialogs (A to 40 s), walk to "Einzelmatch (1 Spieler)", open it,
# then pairs "D-pad right, A" that pick discipline/characters until the event starts. Usage: python rio_event_input.py [end]
import sys
end = int(sys.argv[1]) if len(sys.argv) > 1 else 200
L = [f'{t}:a' for t in range(10, 41, 2)] + ['46:stick=0.5/0.7/1.0'] + [f'{t}:a' for t in (48, 50, 52)]
for t in range(56, end, 2):
    L += [f'{t}:right', f'{t+1}:a']
print(','.join(L))
