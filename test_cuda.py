import torch

# Check if CUDA is available
if torch.cuda.is_available():
    print("CUDA is available!")
    print(f"CUDA Device Name: {torch.cuda.get_device_name(0)}")
    print(f"Number of CUDA Devices: {torch.cuda.device_count()}")
else:
    print("CUDA is not available.")
    
print(torch.version.cuda)
