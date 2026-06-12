import { Box, Container, Typography } from '@mui/material'

function ChatPage() {
  return (
    <Container maxWidth="lg">
      <Box sx={{ mt: 4, mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          GenAI Knowledge Retrieval System
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Chat interface will be implemented here
        </Typography>
      </Box>
    </Container>
  )
}

export default ChatPage
