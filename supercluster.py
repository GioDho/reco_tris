#!/usr/bin/env python
import numpy as np
from skimage.segmentation import  inverse_gaussian_gradient,morphological_geodesic_active_contour,morphological_chan_vese
from clusterTools import Cluster
from scipy.stats import pearsonr
from energyCalibrator import EnergyCalibrator
from cameraChannel import cameraGeometry
import time

class SuperClusterAlgorithm:
    def __init__(self,options,shape,neighbor_window=6):
        self.options = options
        self.shape = shape
        self.neighbor_window = neighbor_window
        self.debug = options.debug_mode
        self.calibrate = self.options.calibrate_clusters
        
        # geometry
        geometryPSet   = open('modules_config/geometry_{det}.txt'.format(det=options.geometry),'r')
        geometryParams = eval(geometryPSet.read())
        self.cg = cameraGeometry(geometryParams)

        # supercluster energy calibration for the saturation effect
        filePar = open('modules_config/energyCalibrator.txt','r')
        params = eval(filePar.read())
        self.calibrator = EnergyCalibrator(params,self.debug)
        
    def clusters_neighborood(self,basic_clusters,raw_data):
        neighboroods = np.zeros([self.shape,self.shape],dtype=float)
        if len(basic_clusters)>0:
           Xtot_clusters = np.vstack(basic_clusters)
           for pointInCluster in Xtot_clusters:
               ix,iy = pointInCluster[0],pointInCluster[1]
               for ixn in range(-self.neighbor_window,self.neighbor_window+1):
                   for iyn in range(-self.neighbor_window,self.neighbor_window+1):
                       x = max(0,min(ix+ixn,self.shape-1))
                       y = max(0,min(iy+iyn,self.shape-1))
                       neighboroods[x,y] = raw_data[x,y]
        return neighboroods

    def store_evolution_in(self,lst):
        """Returns a callback function to store the evolution of the level sets in
        the given list.
        """
        def _store(x):
            lst.append(np.copy(x))
        return _store

    def supercluster(self,clustered_data):
        #print ("clu data = ",clustered_data)
        gimage =inverse_gaussian_gradient(clustered_data,1.5,1.1)
#        print("Fatto")
        # Initial level set
        # this makes alternate squares active at the first iteration of 10 macro-pixels
        #init_ls = checkerboard_level_set(clustered_data.shape, 10)
        init_ls = np.zeros(clustered_data.shape, dtype=np.int8)
        init_ls[10:-10, 10:-10] = 1
        # List with intermediate results for plotting the evolution
        #evolution = []
        #callback = self.store_evolution_in(evolution)
#        ls = morphological_geodesic_active_contour(gimage, 400, init_ls,
#                                                   smoothing=1, balloon=-1,
#                                                   threshold=0.6)
                                                   #iter_callback=callback)
        ls = morphological_chan_vese(gimage, 400, init_ls,
                                     smoothing=1, lambda1=8.,
                                     lambda2=10.)
#        print("Bene!")
        return ls

    def supercluster_points(self,levels):
        from scipy import ndimage as ndi
        # fill the contours of the superclusters
        fill_contours = ndi.binary_fill_holes(levels)
        # remove the smallest superclusters
        label_objects, nb_labels = ndi.label(fill_contours)
        sizes = np.bincount(label_objects.ravel())
        mask_sizes = sizes > 3
        mask_sizes[0] = 0
        contours_cleaned = mask_sizes[label_objects]
        labeled_pixels, nb_labels = ndi.label(contours_cleaned)

        superclusters = [None]*nb_labels
        for ix in range(self.shape):
            for iy in range(self.shape):
                lbl = labeled_pixels[ix,iy]
                if lbl>0: # super-clustered pixel
                    if superclusters[lbl-1]: superclusters[lbl-1].append((ix,iy))
                    else: superclusters[lbl-1] = [(ix,iy)]

        # transform to numpy array
        for isc in range(len(superclusters)):
            superclusters[isc] = np.array(superclusters[isc])
        return np.array(superclusters,dtype=object)

    def findSuperClusters(self,basic_clusters,raw_data,raw_data_fullreso,raw_data_fullreso_zs,iteration):
        superClusters = []; superClusterContours = np.array([])

        if len(basic_clusters):
            # use the clustered points to get "seeds" for superclustering
            # i.e. open a window to get back unclustered points with low light
            seedsAndNeighbors = self.clusters_neighborood(basic_clusters,raw_data)

            # run the superclustering algorithm (GAC with 300 iterations)
            superClusterContours = self.supercluster(seedsAndNeighbors)
          
            # get the superclusters with the list of points of each one
            superClusterWithPixels = self.supercluster_points(superClusterContours)
#            print("A questo punto")
            
            # get a cluster object
            rebin = int(self.cg.npixx/self.shape)
            for i,scpixels in enumerate(superClusterWithPixels):
                #print ("===> SC ",i)
                sclu = Cluster(scpixels,rebin,raw_data_fullreso,raw_data_fullreso_zs,self.options.geometry,debug=False)
                #T2 = time.perf_counter()
                
                sclu.iteration=iteration
                sclu.nclu = i
                sclu.ID=[]
                sclu.IDall=[]
                if sclu.integral()>0 and sclu.hits_fr_zs != []:
                       sclu.nintpixels = sclu.sizeActive()
                       sclu.nallintpixels = sclu.size()
                       for k in range(sclu.nintpixels):
                               sclu.ID.append(i)
                       for k in range(sclu.nallintpixels):
                               sclu.IDall.append(i)
                       sclu.xpixelcoord= sclu.hits_fr_zs[:,0]
                       sclu.ypixelcoord= sclu.hits_fr_zs[:,1]
                       sclu.zpixel= sclu.hits_fr_zs[:,2]
                       sclu.xallpixelcoord= sclu.hits_fr[:,0]
                       sclu.yallpixelcoord= sclu.hits_fr[:,1]
                       sclu.zallpixel= sclu.hits_fr[:,2]
                else:
                       sclu.ID.append(-1)
                       sclu.nintpixels = 1
                       sclu.IDall.append(-1)
                       sclu.nallintpixels = 1
                       if sclu.hits_fr_zs != []:
                            sclu.xpixelcoord= sclu.hits_fr_zs[int(sclu.sizeActive()/2):int(sclu.sizeActive()/2)+1,0]
                            sclu.ypixelcoord= sclu.hits_fr_zs[int(sclu.sizeActive()/2):int(sclu.sizeActive()/2)+1,1]
                            sclu.zpixel= sclu.hits_fr_zs[int(sclu.sizeActive()/2):int(sclu.sizeActive()/2)+1,2]
                       else:
                            sclu.xpixelcoord= sclu.hits_fr[int(sclu.size()/2):int(sclu.size()/2)+1,0]
                            sclu.ypixelcoord= sclu.hits_fr[int(sclu.size()/2):int(sclu.size()/2)+1,1]
                            sclu.zpixel= sclu.hits_fr[int(sclu.size()/2):int(sclu.size()/2)+1,2]
 
                       sclu.xallpixelcoord= sclu.hits_fr[int(sclu.size()/2):int(sclu.size()/2)+1,0]
                       sclu.yallpixelcoord= sclu.hits_fr[int(sclu.size()/2):int(sclu.size()/2)+1,1]
                       sclu.zallpixel= sclu.hits_fr[int(sclu.size()/2):int(sclu.size()/2)+1,2]   

                x = scpixels[:, 0]; y = scpixels[:, 1]
                corr, p_value = pearsonr(x, y)
                sclu.pearson = p_value
                # slicesCalEnergy is useful for the profile along the path
                # this is time-consuming, though
                if self.calibrate:
                    calEnergy,slicesCalEnergy,centers = self.calibrator.calibratedEnergy(sclu.hits_fr)
                    #T3 = time.perf_counter()
                    #print(f"\t calibrated in {T3 - T2:0.4f} seconds")
                else:
                    calEnergy,slicesCalEnergy,centers = -1,[],[]
                if self.debug:
                    print ( "SUPERCLUSTER BARE INTEGRAL = {integral:.1f}".format(integral=sclu.integral()) )
                sclu.calibratedEnergy = calEnergy
                sclu.nslices = len(slicesCalEnergy)
                sclu.energyprofile = slicesCalEnergy
                sclu.centers = centers
                sclu.pathlength = -1 if self.calibrate==False else self.calibrator.clusterLength()
                superClusters.append(sclu)

                # test of the supercluster matcher
                # sclu.dumpToFile('sclu_{i}'.format(i=i),zero_suppressed=True)

                # test of the skeletonization
                # if i==3:
                #     print(" === hits list ")
                #     print(scpixels)
                #     sclu.dumpToFile('supercluster3')

        
        # return the supercluster collection
        return superClusters,superClusterContours
    
