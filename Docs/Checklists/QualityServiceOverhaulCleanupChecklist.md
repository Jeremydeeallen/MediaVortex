# Quality Service Overhaul Cleanup Checklist

## Overview
Complete cleanup and overhaul of the quality testing system, removing all old VMAF references and ensuring the new QualityCompareService works properly.

## Current Issues
- `ModuleNotFoundError: No module named 'Models.VMAFQueueModel'`
- DatabaseManager still references old VMAF models
- Mixed old VMAF code with new quality testing code
- Inconsistent naming and references

## Cleanup Tasks

### **1. Model Cleanup**
- [x] **Check what VMAF models exist** - List all VMAF-related model files
- [x] **Remove VMAF model imports** - Remove imports of non-existent VMAF models from DatabaseManager
- [ ] **Update model references** - Replace VMAF model references with QualityTesting models
- [x] **Create missing models** - Create any missing quality testing models (QualityTestProgressModel, QualityTestResultModel)
- [ ] **Verify model consistency** - Ensure all models follow PascalCase naming

### **2. DatabaseManager Cleanup**
- [ ] **Remove VMAF imports** - Remove `from Models.VMAFQueueModel import VMAFQueueModel`
- [ ] **Remove VMAF methods** - Remove all old VMAF-related methods (GetAllVMAFQueueItems, etc.)
- [ ] **Update method signatures** - Replace VMAF model types with QualityTesting model types
- [ ] **Clean up duplicate methods** - Remove duplicate quality testing methods
- [ ] **Verify method consistency** - Ensure all methods use proper PascalCase naming

### **3. Service Cleanup**
- [ ] **Check service imports** - Verify all services import correct models
- [ ] **Remove VMAF service references** - Remove any remaining VMAF service calls
- [ ] **Update service method calls** - Replace VMAF method calls with QualityTesting equivalents
- [ ] **Verify service consistency** - Ensure all services follow PascalCase naming

### **4. Controller Cleanup**
- [ ] **Check controller imports** - Verify QualityTestingController imports correct services
- [ ] **Update API endpoints** - Ensure all endpoints use correct service methods
- [ ] **Remove VMAF controller references** - Remove any remaining VMAF controller calls
- [ ] **Verify controller consistency** - Ensure all controllers follow PascalCase naming

### **5. ViewModel Cleanup**
- [ ] **Check ViewModel imports** - Verify QualityTestingViewModel imports correct services
- [ ] **Update ViewModel methods** - Replace VMAF method calls with QualityTesting equivalents
- [ ] **Remove VMAF ViewModel references** - Remove any remaining VMAF ViewModel calls
- [ ] **Verify ViewModel consistency** - Ensure all ViewModels follow PascalCase naming

### **6. Database Schema Cleanup**
- [ ] **Check table references** - Verify all database queries use correct table names
- [ ] **Update table names** - Replace VMAFQueue references with QualityTestingQueue
- [ ] **Remove old table references** - Remove any remaining old VMAF table references
- [ ] **Verify schema consistency** - Ensure all database operations use correct schema

### **7. GUI Template Cleanup**
- [ ] **Check template references** - Verify all HTML templates use correct API endpoints
- [ ] **Update JavaScript calls** - Replace VMAF API calls with QualityTesting equivalents
- [ ] **Remove VMAF template references** - Remove any remaining VMAF template elements
- [ ] **Verify template consistency** - Ensure all templates use correct naming

### **8. Microservice Cleanup**
- [ ] **Check microservice imports** - Verify QualityCompareService imports correct services
- [ ] **Update microservice methods** - Replace VMAF method calls with QualityTesting equivalents
- [ ] **Remove VMAF microservice references** - Remove any remaining VMAF microservice calls
- [ ] **Verify microservice consistency** - Ensure all microservice code follows PascalCase naming

### **9. Testing and Validation**
- [ ] **Test microservice startup** - Verify QualityCompareService starts without errors
- [ ] **Test API endpoints** - Verify all QualityTesting API endpoints work
- [ ] **Test GUI integration** - Verify GUI displays quality testing data correctly
- [ ] **Test database operations** - Verify all database operations work correctly
- [ ] **Test service communication** - Verify services communicate properly

### **10. Final Verification**
- [ ] **Run full system test** - Test complete quality testing workflow
- [ ] **Verify no VMAF references** - Search codebase for any remaining VMAF references
- [ ] **Check PascalCase compliance** - Verify all new code follows PascalCase naming
- [ ] **Update documentation** - Update any documentation to reflect new naming
- [ ] **Clean up temporary files** - Remove any temporary or test files

## Priority Order
1. **Models** - Fix missing model imports first
2. **DatabaseManager** - Clean up database layer
3. **Services** - Update service layer
4. **Controllers** - Update API layer
5. **ViewModels** - Update business logic layer
6. **GUI Templates** - Update presentation layer
7. **Microservice** - Update microservice layer
8. **Testing** - Comprehensive testing
9. **Final Verification** - Complete system validation

## Success Criteria
- QualityCompareService starts without errors
- All API endpoints return correct data
- GUI displays quality testing information
- No VMAF references remain in codebase
- All code follows PascalCase naming convention
- Complete quality testing workflow functions properly

## Notes
- This is a complete overhaul, not a migration
- Remove all old VMAF code completely
- Ensure new quality testing system is fully functional
- Maintain MVVM architecture throughout
- Follow strict PascalCase naming conventions
