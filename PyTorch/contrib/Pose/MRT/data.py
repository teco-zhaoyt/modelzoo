import os
import torch.utils.data as data
import torch
import numpy as np

class DATA(data.Dataset):
    def __init__(self, data_path):
        
        train_path = os.path.join(data_path, 'train_3_120_mocap.npy')
        self.data=np.load(train_path, allow_pickle=True)
        
        self.len=len(self.data)
        
        # if joints==15:
        #     use=[0,1,2,3,6,7,8,14,16,17,18,20,24,25,27]
        #     self.data=self.data.reshape(self.data.shape[0],3,-1,31,3)
        #     self.data=self.data[:,:,:,use,:]
        #     self.data=self.data.reshape(self.data.shape[0],3,-1,45)

            
    def __getitem__(self, index):
        
        input_seq=self.data[index][:,:30,:][:,::2,:]#input, 30 fps to 15 fps
        output_seq=self.data[index][:,30:,:][:,::2,:]#output, 30 fps to 15 fps
        last_input=input_seq[:,-1:,:]
        output_seq=np.concatenate([last_input,output_seq],axis=1)

        return input_seq,output_seq
        
        
        
    def __len__(self):
        return self.len



class TESTDATA(data.Dataset):
    def __init__(self, data_path, dataset='mocap'):
        
        if dataset=='mocap':
            tset_path = os.path.join(data_path, 'test_3_120_mocap.npy')
            self.data=np.load(tset_path, allow_pickle=True)
            
        
            # use=[0,1,2,3,6,7,8,14,16,17,18,20,24,25,27]
            # self.data=self.data
            # self.data=self.data.reshape(self.data.shape[0],self.data.shape[1],-1,31,3)
            # self.data=self.data[:,:,:,use,:]
            # self.data=self.data.reshape(self.data.shape[0],self.data.shape[1],-1,45)
        
        if dataset=='mupots':
            test_path = os.path.join(data_path, 'mupots_120_3persons.npy')
            self.data=np.load(test_path, allow_pickle=True)

        self.len=len(self.data)

    def __getitem__(self, index):

        input_seq=self.data[index][:,:30,:][:,::2,:]#input, 30 fps to 15 fps
        output_seq=self.data[index][:,30:,:][:,::2,:]#output, 30 fps to 15 fps
        last_input=input_seq[:,-1:,:]
        output_seq=np.concatenate([last_input,output_seq],axis=1)

        return input_seq,output_seq

    def __len__(self):
        return self.len
