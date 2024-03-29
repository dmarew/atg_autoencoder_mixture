from common import *
from models import *
rect = None
def to_var(x, volatile=False):
	if CUDA_VAILABLE:
		x = x.cuda()
	return Variable(x, volatile=volatile)
def np_to_tensor(x):
	return torch.from_numpy(x)
def cv_to_pil(img):
	img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
	return Image.fromarray(img)
def pil_to_cv(img):
	cv_img  = np.array(img)
	return cv2.cvtColor(cv_img, cv2.COLOR_RGB2BGR)

def cv_to_tensor(img, image_size=IMAGE_SIZE):
	img = cv_to_pil(img)
	trans = transforms.Compose([transforms.Resize((image_size, image_size)),
	                   transforms.ToTensor()])
	return trans(img).unsqueeze(0)
def ros_to_cv(image, bridge):
	return  cv2.cvtColor(bridge.imgmsg_to_cv2(image), cv2.COLOR_BGR2RGB)
def cv_to_ros(image, bridge):
	return  bridge.cv2_to_imgmsg(image)

def tensor_to_cv(tensor):
	pil_image = transforms.functional.to_pil_image(tensor.cpu().squeeze(0))
	return pil_to_cv(pil_image)

def tensor_to_ros(tensor, cv_bridge):
	cv_img =  tensor_to_cv(tensor)
	return cv_bridge.cv2_to_imgmsg(cv_img)

def atg_dict_to_mat(atg, num_aspect_nodes, action_space_size):
	atg_arr = 1e-12 + np.zeros((num_aspect_nodes, action_space_size, num_aspect_nodes),dtype=np.float64)

	for key, value in atg.items():
		s, a, s_prime = key
		atg_arr[s, a, s_prime] = value

	return atg_arr/(np.sum(atg_arr, axis=2, keepdims=True))
def random_action():
	return int(np.random.randint(NUM_ACTIONS))
def im_action(r_a):
	print('before R_a: ', r_a)
	r_a += 1e-8
	r_a/=r_a.sum()
	print('after R_a: ', r_a)
	return int(np.random.choice(np.arange(NUM_ACTIONS), p=r_a))

def simulate_action_with_file(file_path, action_index):
	return int(np.random.randint(action_space))

def imshow(img, display=False):
    npimg = img.cpu().numpy()
    plt.axis('off')
    plt.imshow(np.transpose(npimg, (1, 2, 0)))
    plt.savefig('autoencoder_output.png')
    if display:
        plt.show()
def generate_random_versions_of_image(image, transformer, n_versions=10):
    output = []
    for i in range(n_versions):
        output.append(transformer(image))

    return torch.stack(output)

def get_reconstruction_loss_with_all_ae(image, autoencoder_mixture, loss_fn):
	recon_loss_mix = []
	recon_loss_mix_normalized = []

	for aspect, aspect_param in autoencoder_mixture.items():
		image = to_var(image)
		recon_image = aspect_param['autoencoder'](image)
		if USE_ASPECT_IMAGE and autoencoder_mixture[aspect]['image'] is not None:
			recon_loss  = loss_fn(recon_image, to_var(autoencoder_mixture[aspect]['image'])).cpu().data.sum()
		else:
			recon_loss  = loss_fn(recon_image, image).cpu().data.sum()
		recon_loss_mix.append(recon_loss)
		recon_loss_mix_normalized.append(abs(recon_loss - aspect_param['recon_error']))
	return np.array(recon_loss_mix), np.array(recon_loss_mix_normalized)
def get_recon_likelihood_with_all_ae(image, autoencoder_mixture):
	recon_loss_mix = []
	for aspect, aspect_param in autoencoder_mixture.items():
		image = to_var(image)
		recon_image = aspect_param['autoencoder'](image)
		recon_loss  = stat_of_mse_loss(image, recon_image)[0]
		recon_ll = 1 - scipy.stats.norm(aspect_param['stat'][0], aspect_param['stat'][1]).cdf(recon_loss)
		recon_loss_mix.append(recon_ll)
	return np.array(recon_loss_mix)
def current_aspect_node(recon_loss, aspect_count):
	if np.min(recon_loss) > RECONSTRUCTION_TOLERANCE:
		return aspect_count
	return int(np.where(recon_loss==np.min(recon_loss))[0])
def current_aspect_node_ll(recon_ll):
	if np.max(recon_ll) < RECONSTRUCTION_TOLERANCE_LL:
		return len(recon_ll)
	return np.argmax(recon_ll)
def get_mixure_output(autoencoder_mixture, images, n_clusters=10):
    output = []
    for cluster in range(n_clusters):
        output.append(autoencoder_mixture[cluster]['autoencoder'](images))
    return output
def update_reward(queue, delta_H):
	if len(queue)== MAX_QUEUE_SIZE:
		queue[:-1] = queue[1:]
		queue[-1] = delta_H
	else:
		queue.append(delta_H)
	return queue, np.array(queue).mean()
def reward_dict_to_mat(reward_dict, num_aspect_nodes):
	r_s_a = np.zeros((num_aspect_nodes, len(ACTION_PARAMETER_SPACE)))

	for key, value in reward_dict.items():
		s, a = key
		r_s_a[s, a] = value['mean']
	return 	r_s_a
def belief_for_observation(image, autoencoder_mixture):
    recon_ll = get_recon_likelihood_with_all_ae(image, autoencoder_mixture)
    return belief_from_recon_ll(recon_ll)
def belief_for_observation_old(image, autoencoder_mixture, loss_fn):
    belief = 1./get_reconstruction_loss_with_all_ae(image, autoencoder_mixture, loss_fn)[0]
    belief /= belief.sum()
    return belief
def belief_from_recon_loss(recon_loss):
	belief = 1./recon_loss
	belief /=belief.sum()
	return belief
def belief_from_recon_ll(recon_ll):
	return recon_ll/recon_ll.sum()
def entropy_from_belief(belief):
	return -(belief*np.log(1e-8 + belief)).sum()
def init_autoencoder():
	if CUDA_VAILABLE:
		return nn.Sequential(Encoder(), Decoder()).cuda()
	return nn.Sequential(Encoder(), Decoder())
def init_autoencoder_small():
	if CUDA_VAILABLE:
		return nn.Sequential(SmallEncoder(), SmallDecoder()).cuda()
	return nn.Sequential(SmallEncoder(), SmallDecoder())
def train_autoencoder(autoencoder, optimizer, criterion, data_loader, number_of_epochs=1, name='main', verbose=False):
	print('Training %s ...'%(name))
	for epoch in range(number_of_epochs):

		running_loss = 0.0
		autoencoder.train()
		for batch_index, (in_images, aspect_image) in enumerate(data_loader):

			in_images = to_var(in_images)
			out_images = autoencoder(in_images)
			loss = criterion(out_images, to_var(aspect_image))

			optimizer.zero_grad()
			loss.backward()
			optimizer.step()
			running_loss += loss.cpu().data.numpy()
			if batch_index % 100==0 and verbose:
				print('epoch %d loss: %.5f' % (epoch, running_loss/((batch_index + 1))))
			if batch_index != 0 and batch_index % 1000 == 0:
				break
	autoencoder.eval()
	print('Done training %s'%(name))
def stat_of_mse_loss(input, target):
	batch_size = input.shape[0]
	se = torch.sum((input.view(batch_size, -1) - target.view(batch_size, -1))**2, axis=1)
	return torch.mean(se).cpu().data.numpy(), torch.std(se).cpu().data.numpy()
def generate_atg_graph(atg_mat, aspect_node_images, cv_bridge):
	n_aspects, action_space, _ = atg_mat.shape
	G = nx.MultiDiGraph()
	node_list = ['Aspect_' + str(i) for i in range(n_aspects)]
	for node, aspect_image in zip(node_list, aspect_node_images):
		G.add_node(node, image = ros_to_cv(aspect_image, cv_bridge))
	pos = nx.spring_layout(G)
	labels = {}
	for node_name in node_list:
	    labels[str(node_name)] =str(node_name)
	num_edges = 0
	for s in range(n_aspects):
		for a in range(action_space):
			for s_prime in range(n_aspects):
				if atg_mat[s, a, s_prime]!=0:
					G.add_edge(node_list[s], node_list[s_prime], weight=atg_mat[s, a, s_prime])
					num_edges +=1
	return G, pos, labels, num_edges
def random_image(data_path):
	image_paths = glob.glob(data_path + '*')

	if len(image_paths) > 0:
		image = Image.open(image_paths[int(np.random.randint(len(image_paths)))])
		return to_var(cv_to_tensor(pil_to_cv(image)))
def image_with_index(data_path, index):
	image_path = data_path + str(index) + '.jpg'
	image = Image.open(image_path)
	return to_var(cv_to_tensor(pil_to_cv(image)))
