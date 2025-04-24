from django.shortcuts import render
from django.conf import settings  # To access MEDIA_ROOT if needed directly
import os  # To construct file paths
import math

from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser  # Add JSONParser import
from rest_framework.response import Response

# Import the model from the models module
from .models import UploadedImage, Client,Challenge,UserPost  # Import Client model

# --- AI Model Loading ---
from ultralytics import YOLO
import json
import logging  # Import logging

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Define the model path relative to the Django project's BASE_DIR
# Assuming BASE_DIR is 'c:\Users\bend0\Desktop\My_project\contest\sparkful\sparkful-backend'
# and your model is in 'food_backend\modles\best.pt'
MODEL_PATH = os.path.join(settings.BASE_DIR, 'food_backend', 'models', 'best.pt')  # Adjust this path if needed

# Load the model globally once when the server starts
try:
    if os.path.exists(MODEL_PATH):
        yolo_model = YOLO(MODEL_PATH)
        logger.info(f"Successfully loaded YOLO model from {MODEL_PATH}")
    else:
        yolo_model = None
        logger.error(f"YOLO model file not found at {MODEL_PATH}")
except Exception as e:
    yolo_model = None
    logger.error(f"Error loading YOLO model: {e}", exc_info=True)


# --- Food Health Scores ---
# Dictionary mapping food names (lowercase) to health scores (1-10)
# Based on the provided list, using the final score.
# Load food health scores from score.json

# Path to the score.json file
SCORE_JSON_PATH = os.path.join(settings.BASE_DIR, 'food_backend', 'data', 'score.json')

try:
    with open(SCORE_JSON_PATH, 'r') as f:
        FOOD_HEALTH_SCORES = json.load(f)
    logger.info(f"Successfully loaded food health scores from {SCORE_JSON_PATH}")
except Exception as e:
    FOOD_HEALTH_SCORES = {}
    logger.error(f"Error loading food health scores: {e}", exc_info=True)


# --- AI Inference Function ---
def run_yolo_inference(image_path):
    """
    Runs YOLO inference on the provided image path.

    Args:
        image_path (str): The absolute path to the saved image file.

    Returns:
        dict: A dictionary containing the inference results or an error message.
    """
    logger.info(f"Running YOLO inference on: {image_path}")

    if yolo_model is None:
        logger.error("YOLO model is not loaded. Cannot perform inference.")
        return {"error": "Model not loaded"}

    if not os.path.exists(image_path):
        logger.error(f"Image file not found at: {image_path}")
        return {"error": "Image file not found for inference"}

    try:
        # Perform inference
        results = yolo_model.predict(source=image_path, imgsz=640, conf=0.25)

        detected_objects = []
        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes
            names = result.names

            for i in range(len(boxes)):
                box = boxes[i]
                class_id = int(box.cls)
                class_name = names.get(class_id, "Unknown")
                confidence = float(box.conf)
                bounding_box = box.xyxy[0].tolist()

                # --- Health Score Lookup ---
                lookup_key = class_name.lower()
                health_score = FOOD_HEALTH_SCORES.get(lookup_key)

                detected_objects.append({
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "bounding_box": bounding_box,
                    "health_score": health_score
                })

        logger.info(f"Inference successful. Detected {len(detected_objects)} objects.")
        if not detected_objects:
            logger.info("No objects detected in the image.")
            return {"detections": "No objects detected"}
        return {"detections": detected_objects}

    except Exception as e:
        logger.error(f"Error during YOLO inference: {e}", exc_info=True)
        return {"error": f"Inference failed: {str(e)}"}


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def initialize(request):
    """
    Initializes or updates the client with ID=1, setting their coin count to 30.
    Also initializes two default challenges.
    """
    try:
        # --- Initialize Client ---
        client, client_created = Client.objects.get_or_create(
            id=1,
            defaults={'name': 'Initial Client', 'coin': 30}  # Provide defaults if creating
        )
        if not client_created:
            client.coin = 30
            client.save(update_fields=['coin'])
            logger.info(f"Updated coin for existing Client ID=1 to 30.")
        else:
            logger.info(f"Created new Client with ID=1 and coin=30.")

        # --- Initialize Challenges ---
        challenge1_desc = '減糖挑戰'
        challenge2_desc = '一周不吃炸物挑戰'
        challenge_type = 'official'

        challenge1, challenge1_created = Challenge.objects.get_or_create(
            desc=challenge1_desc,
            defaults={'type': challenge_type}
        )
        if challenge1_created:
            logger.info(f"Created challenge: {challenge1_desc}")
        else:
            # Optionally update the type if it changed, though unlikely for defaults
            if challenge1.type != challenge_type:
                challenge1.type = challenge_type
                challenge1.save(update_fields=['type'])
            logger.info(f"Challenge '{challenge1_desc}' already exists.")

        challenge2, challenge2_created = Challenge.objects.get_or_create(
            desc=challenge2_desc,
            defaults={'type': challenge_type}
        )
        if challenge2_created:
            logger.info(f"Created challenge: {challenge2_desc}")
        else:
            if challenge2.type != challenge_type:
                challenge2.type = challenge_type
                challenge2.save(update_fields=['type'])
            logger.info(f"Challenge '{challenge2_desc}' already exists.")

        return Response({
            "message": f"Client ID=1 {'created' if client_created else 'updated'} and challenges initialized/verified successfully.",
            "client_id": client.id,
            "coin": client.coin,
            "challenges_initialized": [challenge1.desc, challenge2.desc]
        }, status=200)

    except Exception as e:
        logger.error(f"Error during initialization: {e}", exc_info=True)
        return Response({"error": f"Initialization failed: {str(e)}"}, status=500)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def upload_api(request):
    image = request.FILES.get('image')

    logger.info("Received image: %s", image)

    # --- Get Client (Default to ID=1) ---
    try:
        current_client = Client.objects.get(id=1)
        logger.info("Using default client with ID=1")
    except Client.DoesNotExist:
        logger.error("Default client with ID=1 not found.")
        return Response({"error": "Default client not found"}, status=500)

    if not image:
        return Response({"error": "Missing image file"}, status=400)

    # 1. Save image and text to database, linking to client if available
    try:
        # Save the image temporarily to get its full path
        uploaded_data = UploadedImage.objects.create(
            image=image,
            client=current_client
        )
        logger.info(f"Data saved with ID: {uploaded_data.id}, Image path: {uploaded_data.image.path}, Client: {current_client}")
        image_db_id = uploaded_data.id
        image_full_path = uploaded_data.image.path
    except Exception as e:
        logger.error(f"Error saving to database: {e}", exc_info=True)
        return Response({"error": f"Database save error: {str(e)}"}, status=500)

    # 2. Call AI function with the path to the saved image
    ai_results = run_yolo_inference(image_full_path)

    # 3. Update the star field based on AI results
    try:
        if "detections" in ai_results and isinstance(ai_results["detections"], list):
            # Calculate the average health score of detected objects
            health_scores = [
                obj["health_score"] for obj in ai_results["detections"]
                if obj.get("health_score") is not None
            ]
            if health_scores:
                average_score = sum(health_scores) / len(health_scores)
                uploaded_data.stars = math.ceil(average_score / 5)  # Scale to 1-5 stars
                uploaded_data.save()
                logger.info(f"Updated star rating to: {uploaded_data.stars}")
            else:
                # No valid health scores found - delete the uploaded data
                logger.info(f"No valid health scores found in detections. Deleting uploaded data ID: {uploaded_data.id}")
                uploaded_data.delete()
                return Response({
                    "msg": "No valid food items detected in the image",
                    "deleted": True
                }, status=400)
        else:
            # No detections found - delete the uploaded data
            logger.info(f"No detections found. Deleting uploaded data ID: {uploaded_data.id}")
            uploaded_data.delete()
            return Response({
                "msg": "No valid food items detected in the image",
                "deleted": True
            }, status=400)
    except Exception as e:
        logger.error(f"Error updating star rating: {e}", exc_info=True)

    # 4. Return response including AI results
    return Response({
        "msg": "Received successfully and processed",
        "image_name": image.name if image else None,
        "saved_image_path": uploaded_data.image.url,
        "database_id": image_db_id,
        "ai_results": ai_results,
        "star": uploaded_data.stars
    })


@api_view(['GET'])
def get_user_posts(request):
    # Expect a "client_id" query parameter (alternatively use auth session)
    client_id = request.query_params.get('client_id')
    if not client_id:
        return Response({"error": "Missing client_id"}, status=400)
    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return Response({"error": "Client not found"}, status=404)
    posts = client.uploaded_images.all()
    posts_data = [{
        "id": post.id,
        "image_url": post.image.url,
        "text": post.text,
        "uploaded_at": post.uploaded_at
    } for post in posts]
    return Response({"posts": posts_data})


@api_view(['GET'])
def get_challenge(request):
    # Get the challenge type from the request parameters
    challenge_type = request.query_params.get('type')
    try:
        # Fetch the challenge from the database
        challenges = Challenge.objects.all()
        challenge_data = [
            {
            "type": challenge.type,
            "desc": challenge.desc
            }
            for challenge in challenges
        ]
        return Response({"challenge": challenge_data})
    except Challenge.DoesNotExist:
        return Response({"error": "Challenge not found"}, status=404)
    
@api_view(['GET'])
def get_stars(request):
    client_id = request.query_params.get('client_id')
    if not client_id:
        return Response({"error": "Missing client_id"}, status=400)
    try:
        client = Client.objects.get(id=client_id)
        # Get all uploaded images for this client
        uploaded_images = client.uploaded_images.all()
        
        if not uploaded_images.exists():
            return Response({"error": "No images found for this client"}, status=404)
        
        # Get the image with the highest ID (most recent upload)
        # Get image_id from request parameters
        image_id = request.query_params.get('image_id')
        if not image_id:
            return Response({"error": "Missing image_id parameter"}, status=400)
        
        # Find the specific image by ID
        try:
            image = uploaded_images.get(id=image_id)
            return Response({
            "client_id": client_id,
            "image_id": image.id,
            "stars": image.stars
            })
        except UploadedImage.DoesNotExist:
            return Response({"error": f"Image with ID {image_id} not found"}, status=404)
    except Client.DoesNotExist:
        return Response({"error": "Client not found"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])  # Add JSONParser to supported parsers
def upload_post(request):
    '''class UserPost(models.Model):
    coin = models.IntegerField(blank=True, null=True)
    title = models.CharField(max_length=100, blank=True, null=True)
    cost = models.IntegerField(blank=True, null=True)
    share_able = models.BooleanField(default=False)
    desc = models.TextField(blank=True, null=True)
    challenge = models.ForeignKey(Challenge, on_delete=models.SET_NULL, related_name='user_post', blank=True, null=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, related_name='user_post', blank=True, null=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Post {self.id} by {self.client.name if self.client else 'Unknown'}"'''
    form_data = request.data

    # Extract data from the form
    title = form_data.get('title')
    desc = form_data.get('desc')
    coin = form_data.get('coin')
    cost = form_data.get('cost')
    share_able = form_data.get('share_able', False)
    challenge = form_data.get('challenge')
    client_id = form_data.get('client_id')

    # Validate required data
    if not client_id:
        return Response({"error": "Missing client_id"}, status=400)

    try:
        # Get the client
        client = Client.objects.get(id=client_id)
        
        # Get the challenge if a challenge_id was provided
        if challenge:
            try:
                challenge = Challenge.objects.get(desc=challenge)
            except Challenge.DoesNotExist:
                return Response({"error": f"Challenge {challenge} not found"}, status=404)
        
        # Convert data types
        if coin is not None:
            try:
                coin = int(coin)
            except ValueError:
                return Response({"error": "Invalid coin value"}, status=400)
        
        if cost is not None:
            try:
                cost = int(cost)
            except ValueError:
                return Response({"error": "Invalid cost value"}, status=400)
        
        if share_able is not None and isinstance(share_able, str):
            share_able = share_able.lower() == 'true'
        
        # Create the post
        post = UserPost.objects.create(
            title=title,
            desc=desc,
            coin=coin,
            cost=cost,
            share_able=share_able,
            challenge=challenge,
            client=client
        )
        
        # Update client stars (safely handling None values)
        if post.coin:
            if client.coin is None:
                client.coin = post.coin
            else:
                client.coin += post.coin
            # Save the client after updating stars
            client.save()
        
        return Response({
            "message": "Post created successfully",
            "post_id": post.id,
            "title": post.title,
            "client_id": client_id
        }, status=200)
        
    except Client.DoesNotExist:
        return Response({"error": f"Client with ID {client_id} not found"}, status=404)
    except Exception as e:
        logger.error(f"Error creating user post: {e}", exc_info=True)
        return Response({"error": f"Failed to create post: {str(e)}"}, status=500)

@api_view(['GET'])
def get_user_coins(request):
    client_id = request.query_params.get('client_id')
    if not client_id:
        return Response({"error": "Missing client_id"}, status=400)
    try:
        client = Client.objects.get(id=client_id)
        return Response({
            "client_id": client.id,
            "coin": client.coin
        })
    except Client.DoesNotExist:
        return Response({"error": "Client not found"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
@api_view(['GET'])
def initial_test(request):
    # Test endpoint to check if the server is running
    return Response({"message": "Server is running!"})