import torch
from torch import nn

from open_clip import create_model_from_pretrained


class OpenCLIPVisionTower(nn.Module):
    def __init__(self, vision_tower, args, delay_load=False):
        super().__init__()
        assert args.mm_vision_select_layer == -1, "open clip support output tokens of last layer only"

        self.vision_tower_name = vision_tower
        self.select_layer = args.mm_vision_select_layer
        self.select_feature = getattr(args, 'mm_vision_select_feature', 'patch')
        self.hidden_size = None # Place Holder get this value in load_model function
        self.dtype = None # Place Holder get this value in train function
        self.is_loaded = False
        if not delay_load:
            self.load_model()
        
    def load_model(self):
        assert "/" in self.vision_tower_name, """
            vision tower name and pretrained must be split with / in open clip eg: ViT-B-16/laion2b_s34b_b88k"""
        
        model_name, pretrained = self.vision_tower_name.split("/")
        open_clip, self.image_processor = create_model_from_pretrained(model_name, pretrained)
        self.vision_tower = open_clip.visual

        self.hidden_size = self.vision_tower.proj.shape[0] # find the dim before the final proj
        self.vision_tower.output_tokens = True
        self.vision_tower.proj = None # Avoid cls and image patch token dim mismatch
        # self.vision_tower.requires_grad_(False) # TODO, freeze the vision tower?
        self.is_loaded = True
        
    def feature_select(self, image_forward_outs):
        cls_token, patch = image_forward_outs
        if self.select_feature == 'patch':
            image_features = patch
        elif self.select_feature == 'cls_patch':
            image_features = torch.cat((cls_token.unsqueeze(1), patch), dim=1)
        else:
            raise ValueError(f'Unexpected select feature: {self.select_feature}')
        return image_features

    def forward(self, images):
        if type(images) is list:
            image_features = []
            for image in images:
                image_forward_out = self.vision_tower(image.to(device=self.device, dtype=self.dtype).unsqueeze(0))
                image_feature = self.feature_select(image_forward_out).to(image.dtype)
                image_features.append(image_feature)
        else:
            image_forward_outs = self.vision_tower(images.to(device=self.device, dtype=self.dtype))
            image_features = self.feature_select(image_forward_outs).to(images.dtype)

        return image_features

    @property
    def dummy_feature(self):#We want to get back dummy featrues for whatever reason... we need to know the output shape.
        return torch.zeros(1, self.hidden_size, device=self.device, dtype=self.dtype)

    @property
    def device(self):
        return next(self.vision_tower.parameters()).device

    @property
    def num_patches(self):
        return (self.config.image_size // self.config.patch_size) ** 2
