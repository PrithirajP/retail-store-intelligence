import cv2
import numpy as np
import sys

# Store points for the current polygon
points = []

def click_event(event, x, y, flags, params):
    global points
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append([x, y])
        print(f"Point: [{x}, {y}]")
        
        # Draw the point
        cv2.circle(img, (x, y), 5, (0, 0, 255), -1)
        
        # Draw the lines
        if len(points) >= 2:
            cv2.line(img, tuple(points[-2]), tuple(points[-1]), (0, 255, 0), 2)
            
        cv2.imshow('Zone Mapper - Click to draw, Press C to clear, Q to quit', img)

if __name__ == "__main__":

    video_path = "../data/CAM_5.mp4" 
    
    cap = cv2.VideoCapture(video_path)
    success, original_img = cap.read()
    
    if not success:
        print(f"❌ Error: Could not load video at {video_path}")
        print("Please ensure you have placed the raw CCTV .mp4 files in the /data folder.")
        sys.exit(1)

    img = original_img.copy()
    
    cv2.namedWindow('Zone Mapper - Click to draw, Press C to clear, Q to quit', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Zone Mapper - Click to draw, Press C to clear, Q to quit', 1280, 720)
    cv2.setMouseCallback('Zone Mapper - Click to draw, Press C to clear, Q to quit', click_event)
    
    print("\n--- 🗺️ APEX RETAIL ZONE MAPPER ---")
    print("1. Click the corners of a zone (e.g., Billing Desk) in clockwise order.")
    print("2. Press 'c' to clear the current drawing.")
    print("3. Press 'q' to quit and print the coordinates.")
    
    cv2.imshow('Zone Mapper - Click to draw, Press C to clear, Q to quit', img)
    
    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('c'):
            points = []
            img = original_img.copy()
            cv2.imshow('Zone Mapper - Click to draw, Press C to clear, Q to quit', img)

    cv2.destroyAllWindows()
    cap.release()

    if len(points) >= 2:
        print("\n✅ SUCCESS! Copy this array into your configuration:")
        print(f"np.array({points}, np.int32)")
    else:
        print("\nNot enough points clicked.")