from django.db import models

# Model Definition
class Client(models.Model):
    name = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    coin = models.IntegerField(blank=True, null=True)
    num_posts = models.IntegerField(blank=True, null=True, default=0)
    level = models.IntegerField(blank=True, null=True, default=0)

    def __str__(self):
        return self.name if self.name else "Unnamed Client"
    
class Challenge(models.Model):
    type = models.CharField(max_length=100, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    
class UserPost(models.Model):
    coin = models.IntegerField(blank=True, null=True)
    title = models.CharField(max_length=100, blank=True, null=True)
    cost = models.IntegerField(blank=True, null=True)
    share_able = models.BooleanField(default=False)
    desc = models.TextField(blank=True, null=True)
    challenge = models.ForeignKey(Challenge, on_delete=models.SET_NULL, related_name='user_posts', blank=True, null=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, related_name='user_posts', blank=True, null=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Post {self.id} by {self.client.name if self.client else 'Unknown'}"

class UploadedImage(models.Model):
    image = models.ImageField(upload_to='uploads/')
    stars = models.IntegerField(blank=True, null=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, related_name='uploaded_images', blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Updated to use the new field name and access post_id via the related object
        post_identifier = self.user_post.post_id if self.user_post else 'None'
        return f"Image {self.id} for Post {post_identifier}"