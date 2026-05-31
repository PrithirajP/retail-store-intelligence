import cv2
import numpy as np

# List to store the points clicked
points = []

def click_event(event, x, y, flags, params):
    """Callback function to capture mouse clicks."""
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append([x, y])
        print(f"Point recorded: [{x}, {y}]")
        
        # Draw a red dot where you clicked
        cv2.circle(img, (x, y), 5, (0, 0, 255), -1)
        
        # Draw lines connecting the points
        if len(points) > 1:
            cv2.line(img, tuple(points[-2]), tuple(points[-1]), (0, 255, 0), 2)
            
        cv2.imshow('Zone Mapper (Click points, press Q to exit)', img)

if __name__ == "__main__":
    # Change this to whichever camera you are currently mapping
    video_path = "../data/CAM_5.mp4" 
    
    cap = cv2.VideoCapture(video_path)
    success, img = cap.read()
    
    if not success:
        print(f"Error: Could not load video {video_path}")
        exit()

    print("--- ZONE MAPPER TOOL ---")
    print("1. Click the corners of the ZONE in clockwise order.")
    print("2. Press 'q' when you are done.")

    cv2.namedWindow('Zone Mapper (Click points, press Q to exit)', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Zone Mapper (Click points, press Q to exit)', 1280, 720)

    cv2.imshow('Zone Mapper (Click points, press Q to exit)', img)
    cv2.setMouseCallback('Zone Mapper (Click points, press Q to exit)', click_event)
    
    # Wait for the user to press 'q'
    while True:
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()
    cap.release()

    # Print the exact code you need to paste into worker.py
    if len(points) >= 3:
        print("\n✅ SUCCESS! Copy and paste this exact line into your ZONES dictionary in worker.py:\n")
        print(f"np.array({points}, np.int32)")
    else:
        print("\nYou need to click at least 3 points to make a polygon!")