#dependancies pip install lark, pip install python-ifcopenshell, shapely 

#from asyncio.windows_events import NULL
from pickle import FALSE, TRUE
import ifcopenshell
import ifcopenshell.util
import ifcopenshell.util.element
import json
import getopt
import numpy as np
from ifcopenshell.util.selector import Selector
import ifcopenshell.geom
import shapely.geometry as shape_geo
from shapely.geometry import Polygon
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union
import sys
import ifcopenshell.util.placement
import ifcopenshell.util.element
import trimesh
from scipy.spatial import ConvexHull
import difflib


schema = ifcopenshell.ifcopenshell_wrapper.schema_by_name("IFC2X3")


#Some global settings here
selector = Selector()
context = {"@context":["https://raw.githubusercontent.com/SAMSGBLab/iotspaces-DataModels/main/Building/context.json","https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]}
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)
#settings_2d = ifcopenshell.geom.settings()
#settings_2d.set(settings.USE_PYTHON_OPENCASCADE, True)

def aabb_intersect(aabb1, aabb2):
    return np.all(np.less(aabb1[0], aabb2[1])) and np.all(np.less(aabb2[0], aabb1[1]))

def expand_aabb(aabb, tolerance):
    return [aabb[0] - tolerance, aabb[1] + tolerance]

#code to find rooms of floor from https://stackoverflow.com/questions/66906506/finding-children-of-ifcbuildingstorey-using-ifcopenshell
#can be also done by finding proper relationship traversals through the  ifc schema

def getChildrenOfType(ifcParentElement,ifcType):
    items=[]
    if type(ifcType) != list:
        ifcType=[ifcType]
    _getChildrenOfType(items,ifcParentElement,ifcType,0)
    return items

def _getChildrenOfType(targetList,element,ifcTypes,level):
    # follow Spatial relation
    if (element.is_a('IfcSpatialStructureElement')):
        for rel in element.ContainsElements:
            relatedElements = rel.RelatedElements
            for child in relatedElements:
                _getChildrenOfType(targetList,child, ifcTypes, level + 1)
    # follow Aggregation Relation
    if (element.is_a('IfcObjectDefinition')):
        for rel in element.IsDecomposedBy:
            relatedObjects = rel.RelatedObjects
            for child in relatedObjects:
                _getChildrenOfType(targetList,child, ifcTypes, level + 1)
    for typ in ifcTypes:
        if (element.is_a(typ)):
            targetList.append(element)






#Create NGSI-LD attributes (properties,relationships)
def create_ngsi_ld_attribute(Dictionary,Key,Value,Attribute_type):
    if(Value!='' and Value!=[] and Value!=None):
        if(Attribute_type=="Relationship"):
            Dictionary.update({Key: {"type":"Relationship","object":Value}})
        elif(Attribute_type=="Property"):
            Dictionary.update({Key: {"type":"Property","value":Value}})  
        else:
            print("This is an error message")        
    

#usage message
def usage():
    print("""`-f` or `--file`: Specifies the name of the input .ifc file to use/convert.
`-t` or `--test`: Enables internal testing parameters.
`-h` or `--help`: Displays the usage message.
`-d` or `--2D`: Changes the result from 3D to 2D. Note that this option has some issues, so the default 3D is preferred.""")



#MAIN STARTS HERE
def main(argv):
    Dimension_2D= False
    test=False
    filename=''

    try:
        opts, args = getopt.getopt(argv,"f:h:t:d:",["file=","help=","test=","2D="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    #parse command line args
    for opt, arg in opts:
        if opt == '-h':
            usage()
            sys.exit()
        elif opt in ("-f", "-file"):
            #print("I enter here?")
            filename = arg
        elif opt in ("-t", "-test"):
            test=True
        elif opt in ("-d","-2D"):       
            Dimension_2D= True
    print(filename)        
    if filename == '':
       usage()
       sys.exit()

    #filename=filename.rsplit( ".", 1 )[ 0 ]

    #filename= 'AC11-Institute-Var-2-IFC.ifc'
    try:
        ifc = ifcopenshell.open(filename)
    except:
        print("This file is either corrupted or not in ifc form")
        sys.exit()        
    
    filename=filename.rsplit( ".", 1 )[ 0 ]

    if test==True:
        testing_boundary="testing_enabled"
        print("Testing Geometrical Solution for missing relationships enabled!")
    else:
        testing_boundary="testing_disabled"
        print("Testing Geometrical Solution for missing relationships disabled!")
       

    #   sys.exit()
    
    print("File Accepted")
    print("----------------")
    print("STATUS:")
    print("----------------")
    site_not_present=False

    #print(ifc.schema) # May return IFC2X3 or IFC4, maybe change things according to ifc schema detected
    floor_ids=[]
    zone_ids=[]
    room_ids=[]

    try:
        Site = ifc.by_type('IfcSite')[0]
    except:
        site_not_present=True
    #community maybe here
    building= ifc.by_type('IfcBuilding')[0]

    print(building.get_info())
    #Building 
    building_id="urn:ngsi-ld:Building:Test:SmartCitiesdomain:SmartBuildings:" + str(building.GlobalId)

    Building_dictionary={"id":building_id,"type":"Building"}

    create_ngsi_ld_attribute(Building_dictionary,"name",building.Name,"Property")
    create_ngsi_ld_attribute(Building_dictionary,"description",building.Description,"Property")
    if building.BuildingAddress!=None:
        #print(building.BuildingAddress.get_info())
        #print(building.BuildingAddress.AddressLines)
        create_ngsi_ld_attribute(Building_dictionary,"address",str(building.BuildingAddress.AddressLines) + str(building.BuildingAddress.Town) + str(building.BuildingAddress.Region),"Property")

    if(site_not_present==False):
        #longtitude,latitude
        location_Longtitude=Site.RefLongitude
        #print(type(location_Longtitude))
        converted_long=str(location_Longtitude[0])+"."+str(location_Longtitude[1])


        location_latitude=Site.RefLatitude
        #print(type(location_latitude))
        converted_lat=str(location_latitude[0])+"."+str(location_latitude[1])

        location={"coordinates": [
                [float(converted_long),float(converted_lat)]
            ],
            "type": "Point"
            }

        create_ngsi_ld_attribute(Building_dictionary,"location",location,"Property")


    #floorsAboveGround: floorsbelowground
    floorsAboveGround=0
    floorsBelowGround=0

    floors= ifc.by_type('IfcBuildingStorey')

    for floor in floors:
        if floor.Elevation >= 0:
            floorsAboveGround+=1
        else:    
            floorsBelowGround+=1

    create_ngsi_ld_attribute(Building_dictionary,"floorsAboveGround",floorsAboveGround,"Property")
    create_ngsi_ld_attribute(Building_dictionary,"floorsBelowGround",floorsBelowGround,"Property")

    try:
        create_ngsi_ld_attribute(Building_dictionary,"category",ifcopenshell.util.element.get_psets(building)['Pset_BuildingCommon']['OccupancyType'],"Property")
    except:
        dummy_var=0

    Building_dictionary.update(context)

    #print(Building_dictionary)

    # convert into JSON:
    #building_json = json.dumps(Building_dictionary,indent=4)


    # the result is a JSON string:
    #print(building_json)
    print("Building entity Parsed...")
    ##############################BUILDING DONE#####################################################################################################
    ##############################FLOORS START######################################################################################################
    floors_dics=[]

    for floor in floors:
        floor_dictionary={"id":"urn:ngsi-ld:Floor:Test:SmartCitiesdomain:SmartBuildings:" + str(floor.GlobalId),"type":"Floor"}
        floor_ids.append("urn:ngsi-ld:Floor:Test:SmartCitiesdomain:SmartBuildings:" + str(floor.GlobalId))
        create_ngsi_ld_attribute(floor_dictionary,"name",floor.Name,"Property")
        create_ngsi_ld_attribute(floor_dictionary,"description",floor.Description,"Property")

        create_ngsi_ld_attribute(floor_dictionary,"withinBuilding",building_id,"Relationship")
        
        rooms=getChildrenOfType(floor,'IFcSpace')
        roomsOnFloor=[]
        num_of_rooms=0
        floor_vertices=[]
        floor_faces=[]
        two_D_coords=[]

        

        for room in rooms:
            roomsOnFloor.append("urn:ngsi-ld:Room:Test:SmartCitiesdomain:SmartBuildings:" + str(room.GlobalId))
            num_of_rooms+=1
            
            #I make the assumption here that every inch of the floor is covered by one or multiple ifcSpaces
            #Perhaps relative position for floors and zones is redundant

            #shape=(ifcopenshell.geom.create_shape(settings, room))    
            #verts=shape.geometry.verts
            #faces=shape.geometry.faces
            #grouped_verts = [[verts[i], verts[i + 1], verts[i + 2]] for i in range(0, len(verts), 3)]
            #grouped_faces = [[faces[i], faces[i + 1], faces[i + 2]] for i in range(0, len(faces), 3)] 
            #floor_vertices.append(grouped_verts)
            #floor_faces.append(grouped_faces)
            #two_D_poly_test=shape_geo.Polygon(grouped_verts)
            #print(two_D_poly_test.is_valid)
            #pp2 = two_D_poly_test.buffer(0)
            #print(pp2.is_valid)
            #two_D_coords.append(pp2)
        
        #relative_position_2D = shape_geo.Polygon()
        #for coords in two_D_coords: 
        #    relative_position_2D= relative_position_2D.union(coords)
        
        #relative_position_2D = unary_union(two_D_coords)
        #relative_position_2Db=relative_position_2D.convex_hull
        #print(json.dumps(shape_geo.mapping(relative_position_2D)))

        #print(floor_shape)
        if num_of_rooms!=0:
            create_ngsi_ld_attribute(floor_dictionary,"roomsOnFloor",roomsOnFloor,"Relationship")
            create_ngsi_ld_attribute(floor_dictionary,"numberOfRooms",num_of_rooms,"Property")

        floor_dictionary.update(context)
        # convert into JSON:
        #floor_json = json.dumps(floor_dictionary,indent=4)
        floors_dics.append(floor_dictionary)

    #print(ifc.get_inverse(floor))
    # the result is a JSON string:

    #print(floors_dics)

    print("Floor entities Parsed...")
    ###########################################################FLOORS DONE#########################################################################################
    ###########################################################ZONE START##########################################################################################
    zone_dics=[]
    zones = ifc.by_type('IfcZone')

    Zones_of_room={}


    for zone in zones:
        zone_id="urn:ngsi-ld:Zone:Test:SmartCitiesdomain:SmartBuildings:" + str(zone.GlobalId)
        zone_ids.append(zone_id)
        zone_dictionary={"id":zone_id,"type":"Zone"}
        create_ngsi_ld_attribute(zone_dictionary,"name",zone.Name,"Property")
        create_ngsi_ld_attribute(zone_dictionary,"description",zone.Description,"Property")
        create_ngsi_ld_attribute(zone_dictionary,"withinBuilding",building_id,"Relationship")

        
        roomsInZone=[]
        num_of_rooms=0
        floor_vertices=[]
        floor_faces=[]
        two_D_coords=[]


        test=ifc.get_inverse(zone)

        #print(test[0].get_info())
        t=test[0].get_info()

        #print(t["RelatedObjects"])
        for spaces in t["RelatedObjects"]:
            room_id=spaces.get_info()["GlobalId"]
            #print(spaces.get_info())
        
            roomsInZone.append("urn:ngsi-ld:Room:Test:SmartCitiesdomain:SmartBuildings:" + str(room_id))
            num_of_rooms+=1
            Zones_of_room.setdefault(room_id,[]).append(zone_id)
        #     print(Zones_of_room)
        create_ngsi_ld_attribute(zone_dictionary,"roomsInZone",roomsInZone,"Relationship")

    

        zone_dictionary.update(context)

        #zone_json = json.dumps(zone_dictionary,indent=4)
        zone_dics.append(zone_dictionary)

    #print(zone_dics)

    #for key in test[0].get_info():
    print("Zone entities Parsed...")    
    ############################################################################## ZONES DONE #########################################################################
    ############################################################################## ROOMS START########################################################################

    stairs_of_floor={}
    trimeshes_of_floor_objects={}
    Objects_of_floor_id={}
    objects_of_floor=[]
    trimeshes_of_stairs=[]
    stairs_ids=[]
    stairs_of_floor_id={}

    room_dics=[]
    rooms = ifc.by_type('IfcSpace')

    #print(Zones_of_room)
    for room in rooms:

        #print(room.get_info())
        room_dictionary={"id":"urn:ngsi-ld:Room:Test:SmartCitiesdomain:SmartBuildings:" + str(room.GlobalId),"type":"Room"}
        room_ids.append("urn:ngsi-ld:Room:Test:SmartCitiesdomain:SmartBuildings:" + str(room.GlobalId))
        create_ngsi_ld_attribute(room_dictionary,"name",room.Name,"Property")
        create_ngsi_ld_attribute(room_dictionary,"description",room.Description,"Property")

        try:
            create_ngsi_ld_attribute(room_dictionary,"inZone",Zones_of_room[room.GlobalId],"Relationship")
        except:
            #Room doesn't belong to a zone
            dummy_var=0
        #print('Room',room.Name,' is at floor:',room.Decomposes[0][4][2])

        
        #Potential for multiple floors same room?
        create_ngsi_ld_attribute(room_dictionary,"onFloor","urn:ngsi-ld:Floor:Test:SmartCitiesdomain:SmartBuildings:"+room.Decomposes[0][4][0],"Relationship")
        

        #relative position of room
        shape=(ifcopenshell.geom.create_shape(settings, room))    
        verts=shape.geometry.verts
        faces=shape.geometry.faces
        grouped_verts = [[verts[i], verts[i + 1], verts[i + 2]] for i in range(0, len(verts), 3)]
        grouped_faces = [[faces[i], faces[i + 1], faces[i + 2]] for i in range(0, len(faces), 3)] 
        
        trimesh_of_room=trimesh.base.Trimesh(vertices=grouped_verts,faces=grouped_faces) 
        

        #TODO import measurement unit from ifc here
        if(Dimension_2D==False):
            create_ngsi_ld_attribute(room_dictionary,"relativePosition",{"type": "Trimesh","measurementUnit": "m",
                "Dimensions": "3D","coordinates":grouped_verts,"faces":grouped_faces},"Property")
        else:
            verts_2d=[[verts[i], verts[i + 1]] for i in range(0, len(verts), 3)]
            #print(verts_2d)
            # Compute convex hull
            #hull = ConvexHull(verts_2d)

            #verts_2d = list(set(tuple(x) for x in verts_2d))
            #verts_2d = [list(x) for x in verts_2d]
            unique_verts = []
            for vert in verts_2d:
                if vert not in unique_verts:
                    unique_verts.append(vert)
            verts_2d=unique_verts        
            
            # Get vertices of convex hull
            #print(hull.vertices)
            
            #hull_verts = [verts_2d[i] for i in hull.vertices]
            #print(hull_verts)
            
            # Get the number of vertices in the convex hull
            #num_vertices = len(hull.vertices)

            #let me check
           
            # Project vertices onto 2D plane
            num_vertices = len(verts_2d)

            # Set the type variable based on the number of vertices
            if num_vertices == 1:
                typedim = "Point"
            elif num_vertices == 2:
                typedim = "LineString"
            else:
                typedim = "Polygon"
                #hull_verts.append(hull_verts[0])
                verts_2d.append(verts_2d[0])

            #print(verts_2d)    
            #print(hull_verts)


            create_ngsi_ld_attribute(room_dictionary,"relativePosition",{"type": typedim,"measurementUnit": "m",
                "Dimensions": "2D","coordinates":verts_2d},"Property")

        num_of_doors=0
        num_of_windows=0

        doors_of_room=[]
        windows_of_room=[]
        stairs_of_room=[]
        #find doors and windows
        inverse_of_room=ifc.get_inverse(room)
        found_boundary=0
        
        
        for rels in inverse_of_room:
            if(rels.is_a("IFcRelSpaceBoundary")):
                found_boundary=1
                try:
                    if rels.get_info()['RelatedBuildingElement'].is_a("IfcDoor"):
                        num_of_doors+=1
                        doors_of_room.append("urn:ngsi-ld:Door:Test:SmartCitiesdomain:SmartBuildings:" + rels.get_info()['RelatedBuildingElement'].GlobalId)
                    elif rels.get_info()['RelatedBuildingElement'].is_a("IfcWindow"):
                        num_of_windows+=1
                        windows_of_room.append("urn:ngsi-ld:Window:Test:SmartCitiesdomain:SmartBuildings:" + rels.get_info()['RelatedBuildingElement'].GlobalId) 
                except:
                    continue       
        
       
        #if no relationships for room present in file, try to find using geometrical calculations
        if (found_boundary==0 and testing_boundary=="testing_enabled"):
            #I really have no memory of what I did here
            print("No relationships found for room, trying geometrical solution")
            print("Testing Boundaries...")
            

            objects = selector.parse(ifc, '@ #'+ room.Decomposes[0][4][0]+ ' & (.IfcDoor | .ifcWindow) ')   
            
            #print(objects)

            
            for object in objects:
                #if object in room, add to objects
                shape2=(ifcopenshell.geom.create_shape(settings, object))    
                verts2=shape2.geometry.verts
                faces2=shape2.geometry.faces
                grouped_verts2 = [[verts2[i], verts2[i + 1], verts2[i + 2]] for i in range(0, len(verts2), 3)]
                grouped_faces2 = [[faces2[i], faces2[i + 1], faces2[i + 2]] for i in range(0, len(faces2), 3)] 

                #print(object)
                #trimesh_of_object=trimesh.base.Trimesh(vertices=grouped_verts2,faces=grouped_faces2) 
                #trimeshes_of_floor_objects.setdefault(room.Decomposes[0][4][0],[]).append(trimesh_of_object)
                #bjects_of_floor_id.setdefault(room.Decomposes[0][4][0],[]).append(object.GlobalId)
                #touching=trimesh.boolean.intersection([trimesh_of_room,trimesh_of_object],"blender")

                # Create trimesh objects
                trimesh_of_object = trimesh.base.Trimesh(vertices=grouped_verts2, faces=grouped_faces2)
                trimesh_of_room_aabb = trimesh_of_room.bounds
                trimesh_of_object_aabb = trimesh_of_object.bounds

                # Define the tolerance value (e.g., 0.1 meters)
                tolerance = 0.3
                trimesh_of_room_aabb_expanded = expand_aabb(trimesh_of_room_aabb, tolerance)

                # Check if bounding boxes intersect
                bb_intersection = aabb_intersect(trimesh_of_room_aabb_expanded, trimesh_of_object_aabb)

                # If the bounding boxes intersect, perform the actual mesh intersection test
                if bb_intersection:
                    touching = True
                else:
                    touching = False
                
                if (touching != False ):
                    

                    if(object.is_a('IfcDoor')):
                        print("Door found")
                    #lookthismoreclosely
                    #check type of object and append accordingly
                        doors_of_room.append("urn:ngsi-ld:Door:Test:SmartCitiesdomain:SmartBuildings:"+ object.GlobalId)
                        num_of_doors+=1
                    elif(object.is_a("IfcWindow")):
                        print("Window found")
                    #lookthismoreclosely
                    #check type of object and append accordingly
                        windows_of_room.append("urn:ngsi-ld:Door:Test:SmartCitiesdomain:SmartBuildings:"+ object.GlobalId)   
                        num_of_windows+=1 
                    else:
                        print("WARNING MAJOR ERROR IN LOGIC, DOOR or WINDOW EXPECTED BUT NOT FOUND")
        
        
        #stairs in room, get stairs of floor first

        #if already found stairs of the floor the area is in
        #need to find a better way to calculate this
        temporary_bypass=0
        if(temporary_bypass!=1):
            try:
                trimeshes_of_stairs= stairs_of_floor[room.Decomposes[0][4][0]]
                stairs_ids= stairs_of_floor_id[room.Decomposes[0][4][0]]
                count=0
                for stair_mesh in trimeshes_of_stairs:
                    touching=trimesh.boolean.intersection([trimesh_of_room,stair_mesh],"blender")
                    #print(touching)
                    #print("locally cached")
                    if (touching.is_empty == False):
                        print("Stairs found")
                        stairs_of_room.append("urn:ngsi-ld:Stair:Test:SmartCitiesdomain:SmartBuildings:"+ stairs_ids[count])
                    count=count+1    
            except:
                #print(room.Decomposes[0][4][0])
                stairs = selector.parse(ifc, '@ #'+ room.Decomposes[0][4][0]+ ' & .IfcStair ')   
                once=1
                for stair in stairs:

                    #print(stair.ShapeType)
                    #print(stair.IsDefinedBy)
                    #print(ifc.traverse(stair, max_levels=1))
                    #if stair in room then add to stairs

                    if(stair.ShapeType=="NOTDEFINED"):
                        
                        stair_components = stair.IsDecomposedBy[0].RelatedObjects

                        for stair_element in stair_components:
                            if 'IfcStairFlight' == stair_element.is_a():
                                nothing_for_now=0

                    else:    
                        shape2=(ifcopenshell.geom.create_shape(settings, stair))    
                        verts2=shape2.geometry.verts
                        faces2=shape2.geometry.faces
                        grouped_verts2 = [[verts2[i], verts2[i + 1], verts2[i + 2]] for i in range(0, len(verts2), 3)]
                        grouped_faces2 = [[faces2[i], faces2[i + 1], faces2[i + 2]] for i in range(0, len(faces2), 3)] 

                        trimesh_of_stair=trimesh.base.Trimesh(vertices=grouped_verts2,faces=grouped_faces2) 
                        stairs_of_floor.setdefault(room.Decomposes[0][4][0],[]).append(trimesh_of_stair)
                        stairs_of_floor_id.setdefault(room.Decomposes[0][4][0],[]).append(stair.GlobalId)
                        touching=trimesh.boolean.intersection([trimesh_of_room,trimesh_of_stair],"blender")
                        print(touching)
                        if (touching.is_empty == False):
                            print("Stairs found")
                            stairs_of_room.append("urn:ngsi-ld:Stair:Test:SmartCitiesdomain:SmartBuildings:"+ stair.GlobalId)

       
        create_ngsi_ld_attribute(room_dictionary,"DoorsInRoom",doors_of_room,"Relationship") 
                      
        create_ngsi_ld_attribute(room_dictionary,"windowsInRoom",windows_of_room,"Relationship")
        
        create_ngsi_ld_attribute(room_dictionary,"StairsInRoom",stairs_of_room,"Relationship")      
        create_ngsi_ld_attribute(room_dictionary,"numberOfDoors",num_of_doors,"Property")
        create_ngsi_ld_attribute(room_dictionary,"numberOfWindows",num_of_windows,"Property")

        

        room_dictionary.update(context)

        #room_json = json.dumps(room_dictionary,indent=4)
        room_dics.append(room_dictionary)


        #print(test[0].get_info())
    #t=test[0].get_info()
    #print(t)
    #print(room_dics[0])
    print("Room entities Parsed...")
    ############################################################################# ROOMS END########################################################################
    ############################################################################# Doors START########################################################################
    door_dics=[]
    Doors = ifc.by_type('IfcDoor')

    for door in Doors:
        door_dictionary={"id":"urn:ngsi-ld:Door:Test:SmartCitiesdomain:SmartBuildings:" + str(door.GlobalId),"type":"Door"}
        shape=(ifcopenshell.geom.create_shape(settings, door))    
        verts=shape.geometry.verts
        faces=shape.geometry.faces
        grouped_verts = [[verts[i], verts[i + 1], verts[i + 2]] for i in range(0, len(verts), 3)]
        grouped_faces = [[faces[i], faces[i + 1], faces[i + 2]] for i in range(0, len(faces), 3)]

        if(Dimension_2D==False):
            create_ngsi_ld_attribute(door_dictionary,"relativePosition",{"type": "Trimesh","measurementUnit": "m",
                "Dimensions": "3D","coordinates":grouped_verts,"faces":grouped_faces},"Property")
        else:
            verts_2d=[[verts[i], verts[i + 1]] for i in range(0, len(verts), 3)]
            #print(verts_2d)
            # Compute convex hull
            hull = ConvexHull(verts_2d)

            # Get vertices of convex hull
            #print(hull.vertices)
            hull_verts = [verts_2d[i] for i in hull.vertices]
            #print(hull_verts)
            # Get the number of vertices in the convex hull
            num_vertices = len(hull.vertices)

            # Set the type variable based on the number of vertices
            if num_vertices == 1:
                typedim = "Point"
            elif num_vertices == 2:
                typedim = "LineString"
            else:
                typedim = "Polygon"
                hull_verts.append(hull_verts[0])

            create_ngsi_ld_attribute(door_dictionary,"relativePosition",{"type": typedim,"measurementUnit": "m",
                "Dimensions": "2D","coordinates":hull_verts},"Property")

        door_dictionary.update(context)

        #door_json = json.dumps(door_dictionary,indent=4)
        door_dics.append(door_dictionary)

    #print(door_dics[0])

    print("Door entities Parsed...")
    ############################################################################# Doors END########################################################################
    ############################################################################# Windows START########################################################################
    Window_dics=[]
    Windows = ifc.by_type('IfcWindow')

    for Window in Windows:
        Window_dictionary={"id":"urn:ngsi-ld:Window:Test:SmartCitiesdomain:SmartBuildings:" + str(Window.GlobalId),"type":"Window"}
        shape=(ifcopenshell.geom.create_shape(settings, Window))    
        verts=shape.geometry.verts
        faces=shape.geometry.faces
        grouped_verts = [[verts[i], verts[i + 1], verts[i + 2]] for i in range(0, len(verts), 3)]
        grouped_faces = [[faces[i], faces[i + 1], faces[i + 2]] for i in range(0, len(faces), 3)]

        if(Dimension_2D==False):
            create_ngsi_ld_attribute(Window_dictionary,"relativePosition",{"type": "Trimesh","measurementUnit": "m",
                "Dimensions": "3D","coordinates":grouped_verts,"faces":grouped_faces},"Property")
        else:
            verts_2d=[[verts[i], verts[i + 1]] for i in range(0, len(verts), 3)]
            #print(verts_2d)
            # Compute convex hull
            hull = ConvexHull(verts_2d)

            # Get vertices of convex hull
            #print(hull.vertices)
            hull_verts = [verts_2d[i] for i in hull.vertices]
            #print(hull_verts)
            # Get the number of vertices in the convex hull
            num_vertices = len(hull.vertices)

            # Set the type variable based on the number of vertices
            if num_vertices == 1:
                typedim = "Point"
            elif num_vertices == 2:
                typedim = "LineString"
            else:
                typedim = "Polygon"
                hull_verts.append(hull_verts[0])
            #print(hull_verts)    
            create_ngsi_ld_attribute(Window_dictionary,"relativePosition",{"type": typedim,"measurementUnit": "m",
                "Dimensions": "2D","coordinates":hull_verts},"Property")


    

        Window_dictionary.update(context)

        #Window_json = json.dumps(Window_dictionary,indent=4)
        
        #Window_dics.append(Window_json)
        Window_dics.append(Window_dictionary)

    #print(Window_dics[0])
    print("Window entities Parsed...")    
    ############################################################################# Windows END########################################################################
    ############################################################################# Stairs Start#######################################################################
    Stair_dics=[]
    Stairs = ifc.by_type('IfcStair')
    
    #print(Stairs)
    for Stair in Stairs:
        Stair_dictionary={"id":"urn:ngsi-ld:Stair:Test:SmartCitiesdomain:SmartBuildings:" + str(Stair.GlobalId),"type":"Stair"}

        if(stair.ShapeType=="NOTDEFINED"):
            stair_components = Stair.IsDecomposedBy[0].RelatedObjects
            verts2=[]
            faces2=[]
            faces3=[]
            maxi=0
            for stair_element in stair_components:
                if 'IfcStairFlight' == stair_element.is_a():
                    shape2=(ifcopenshell.geom.create_shape(settings, stair_element))

                    verts3=(shape2.geometry.verts)
                    #print(len(verts3))
                    #previous_face_len=len(faces3)
                    if faces3!=[]:
                        maxi=max(faces3)

                    faces3=(shape2.geometry.faces)
                    faces3 = [x + maxi for x in faces3]
                    #print(faces3)
                    verts2.extend(verts3)
                    faces2.extend(faces3)
                    
                #print(verts2)
                #print(Stair)
                #print(len(verts2))
                
            grouped_verts = ([[verts2[i], verts2[i + 1], verts2[i + 2]] for i in range(0, len(verts2), 3)])
            grouped_faces = ([[faces2[i], faces2[i + 1], faces2[i + 2]] for i in range(0, len(faces2), 3)])

            if(Dimension_2D==False):
                create_ngsi_ld_attribute(Stair_dictionary,"relativePosition",{"type": "Trimesh","measurementUnit": "m",
                "Dimensions": "3D","coordinates":grouped_verts,"faces":grouped_faces},"Property")
            else:
                verts_2d=[[verts[i], verts[i + 1]] for i in range(0, len(verts), 3)]
                #print(verts_2d)
                # Compute convex hull
                hull = ConvexHull(verts_2d)

                # Get vertices of convex hull
                #print(hull.vertices)
                hull_verts = [verts_2d[i] for i in hull.vertices]
                #print(hull_verts)
                # Get the number of vertices in the convex hull
                num_vertices = len(hull.vertices)

                # Set the type variable based on the number of vertices
                if num_vertices == 1:
                    typedim = "Point"
                elif num_vertices == 2:
                    typedim = "LineString"
                else:
                    typedim = "Polygon"
                    hull_verts.append(hull_verts[0])

                create_ngsi_ld_attribute(Stair_dictionary,"relativePosition",{"type": typedim,"measurementUnit": "m",
                    "Dimensions": "2D","coordinates":hull_verts},"Property")
                                  
        else:
            shape=(ifcopenshell.geom.create_shape(settings, Stair))    
            verts=shape.geometry.verts
            faces=shape.geometry.faces
            grouped_verts = [[verts[i], verts[i + 1], verts[i + 2]] for i in range(0, len(verts), 3)]
            grouped_faces = [[faces[i], faces[i + 1], faces[i + 2]] for i in range(0, len(faces), 3)]
           
            if(Dimension_2D==False):
                create_ngsi_ld_attribute(Stair_dictionary,"relativePosition",{"type": "Trimesh","measurementUnit": "m",
                "Dimensions": "3D","coordinates":grouped_verts,"faces":grouped_faces},"Property")
            else:
                verts_2d=[[verts[i], verts[i + 1]] for i in range(0, len(verts), 3)]
                #print(verts_2d)
                # Compute convex hull
                hull = ConvexHull(verts_2d)

                # Get vertices of convex hull
                #print(hull.vertices)
                hull_verts = [verts_2d[i] for i in hull.vertices]
                #print(hull_verts)
                # Get the number of vertices in the convex hull
                num_vertices = len(hull.vertices)

                # Set the type variable based on the number of vertices
                if num_vertices == 1:
                    typedim = "Point"
                elif num_vertices == 2:
                    typedim = "LineString"
                else:
                    typedim = "Polygon"
                    hull_verts.append(hull_verts[0])

                create_ngsi_ld_attribute(Stair_dictionary,"relativePosition",{"type": typedim,"measurementUnit": "m",
                    "Dimensions": "2D","coordinates":hull_verts},"Property")

        Stair_dictionary.update(context)

        #Window_json = json.dumps(Window_dictionary,indent=4)
        
        #Window_dics.append(Window_json)
        Stair_dics.append(Stair_dictionary)


        

    ############################################################################ Stairs End ########################################################################
    print("Stair entities Parsed...")

    #extra building relationships here
    create_ngsi_ld_attribute(Building_dictionary,"HasFloors",floor_ids,"Relationship")
    create_ngsi_ld_attribute(Building_dictionary,"HasZones",zone_ids,"Relationship")
    create_ngsi_ld_attribute(Building_dictionary,"HasRooms",room_ids,"Relationship")

    building_json = json.dumps(Building_dictionary,indent=4)
    print("----------------------")
    print("All done, writing results to appropriate files...")
    #Write to ngsi-ld files

            
    with open(filename+"_Building.ngsild", 'w') as f:
        f.write(str(building_json))
    with open(filename+"_Floors.ngsild", 'w') as f:
        f.write(json.dumps(floors_dics,indent=4))
    with open(filename+"_Zones.ngsild", 'w') as f:
        f.write(json.dumps(zone_dics,indent=4))
    with open(filename+"_Rooms.ngsild", 'w') as f:
        f.write(json.dumps(room_dics,indent=4))
    with open(filename+"_Windows.ngsild", 'w') as f:
        f.write(json.dumps(Window_dics,indent=4))
    with open(filename+"_Doors.ngsild", 'w') as f:
        f.write(json.dumps(door_dics,indent=4))
    with open(filename+"_Stairs.ngsild", 'w') as f:
        f.write(json.dumps(Stair_dics,indent=4))                  





if __name__ == "__main__":
   main(sys.argv[1:])
