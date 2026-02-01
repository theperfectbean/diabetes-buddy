# Knowledge Sources Configuration

## Overview

This document outlines the knowledge sources used by Diabetes Buddy and their configuration.

## Source Collections

### Clinical Guidelines (High Priority)
- **ADA Standards of Care**: Trust level 1.0 (highest priority)
- **Australian Diabetes Guidelines**: Trust level 1.0 (highest priority)

### Research Literature
- **PubMed Research Papers**: Trust level 0.7 (peer-reviewed but abstracts only)

### Educational Content
- **Wikipedia T1D Education**: Trust level 0.8 (educational, may be edited)

### Community Documentation (Lower Priority)
- **OpenAPS Documentation**: Trust level 0.6 (community-developed, product-specific)
- **Loop Documentation**: Trust level 0.6 (community-developed, product-specific)
- **AndroidAPS Documentation**: Trust level 0.6 (community-developed, product-specific)

### User-Uploaded Sources
- **User PDFs**: Trust level 0.9 (user-provided device manuals and guides)

## Decision: OpenAPS/Loop/AndroidAPS Confidence Adjustment

**Date:** February 1, 2026  
**Decision:** Reduced confidence from 0.8 to 0.6 for OpenAPS, Loop, and AndroidAPS documentation collections.

**Rationale:**
- These collections contain product-specific information that may not be applicable to all users
- As Diabetes Buddy moves toward product-agnostic recommendations, these sources should have lower priority
- Clinical guidelines (ADA) and user-uploaded manuals should take precedence
- The collections are retained for cases where they provide general diabetes management principles that can be adapted

**Alternative Considered:**
- Complete removal of these collections
- Decision: Keep with reduced confidence to maintain access to community-developed knowledge while prioritizing clinical guidelines and user-specific documentation

## Future Considerations

- Monitor usage patterns to determine if further confidence adjustments are needed
- Consider adding more clinical guideline sources
- Evaluate the effectiveness of user-uploaded PDF system